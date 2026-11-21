"""Run bounded Gemini and AlphaGenome smoke probes with public or synthetic inputs."""
from __future__ import annotations

import argparse
import base64
import io
import json
import time
from pathlib import Path

from genesleuth import config


READ_DATE = "2026-11-21"
SCORERS = ("RNA_SEQ", "SPLICE_SITES", "SPLICE_SITE_USAGE", "SPLICE_JUNCTIONS")
ECHO = {
    "type": "function",
    "name": "measure",
    "description": "Return the submitted label unchanged.",
    "parameters": {
        "type": "object",
        "properties": {"label": {"type": "string"}},
        "required": ["label"],
    },
}
PNG_CHECK = {
    "inscription": {"type": "noul", "instructions": "Does the image say CEDAR 214?"},
    "route": {
        "type": "choice",
        "instructions": "Choose the kind of document.",
        "criteria": {"test_card": "A short label on a white test card", "other": "Anything else"},
    },
    "legibility": {
        "type": "score",
        "instructions": "How legible is the text?",
        "criteria": ["unreadable", "partly legible", "clearly legible"],
    },
}


def measure(name, action):
    """Record a typed outcome and latency without copying SDK error bodies."""
    start = time.monotonic()
    try:
        result = {"status": "ok", "result": action()}
    except Exception as error:
        result = {"status": "error", "error_type": type(error).__name__}
        if isinstance(getattr(error, "code", None), int):
            result["http_status"] = error.code
    return {"probe": name, "seconds": round(time.monotonic() - start, 3), **result}


def media_bytes(kind):
    """Create a test image, text PDF or image-only PDF in memory."""
    from PIL import Image, ImageDraw
    from reportlab.pdfgen import canvas

    output = io.BytesIO()
    if kind == "text_pdf":
        page = canvas.Canvas(output)
        page.drawString(60, 720, "Synthetic referral: seizures first appeared at age 4.")
        page.save()
    else:
        image = Image.new("RGB", (420, 160), "white")
        ImageDraw.Draw(image).text((55, 55), "CEDAR 214", fill="black", font_size=32)
        image.save(output, format="PNG" if kind == "png" else "PDF")
    return output.getvalue()


def inline(kind):
    """Encode a supported Gemini inline content block."""
    return {
        "type": "image" if kind == "png" else "document",
        "mime_type": "image/png" if kind == "png" else "application/pdf",
        "data": base64.b64encode(media_bytes(kind)).decode("ascii"),
    }


def function_results(steps, *, managed=False):
    """Respond once to each native function call without any external actions."""
    answered = {getattr(step, "call_id", None) for step in (steps or []) if step.type == "function_result"}
    return [
        {
            "type": "function_result",
            "name": step.name,
            "call_id": step.id,
            "result": step.arguments if managed else [{"type": "text", "text": json.dumps(step.arguments)}],
        }
        for step in steps or []
        if step.type == "function_call" and step.id not in answered
    ]


def gemini_tests():
    """Construct documented Gemini probes after validating prerequisites."""
    from google import genai

    if not config.GEMINI_API_KEY:
        raise PermissionError("Gemini key missing")
    client = genai.Client(api_key=config.GEMINI_API_KEY, http_options={"api_version": "v1", "timeout": 30_000})
    beta = genai.Client(api_key=config.GEMINI_API_KEY, http_options={"api_version": "v1beta", "timeout": 45_000})

    def structured(model, input_data):
        """Check text plus structured output and the returned model version."""
        response = client.interactions.create(
            model=model,
            input=input_data,
            generation_config={"thinking_level": "medium"},
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                },
            },
        )
        return {
            "answer": json.loads(response.output_text)["answer"],
            "model_version": getattr(response, "model_version", None),
        }

    def tools_round_trip():
        """Verify native function calling, stateful results and parallel requests."""
        response = client.interactions.create(
            model=config.NEON,
            input="Call measure twice in parallel with labels red and blue, then report both results.",
            tools=[ECHO],
            generation_config={"thinking_level": "medium"},
        )
        replies = function_results(response.steps)
        if not replies:
            raise ValueError("The model did not produce tool calls")
        final = client.interactions.create(
            model=config.NEON,
            previous_interaction_id=response.id,
            input=replies,
            tools=[ECHO],
        )
        return {"parallel_function_calls": len(replies), "output": final.output_text}

    def decisions(input_data):
        """Check merged question types and the SDK response fields."""
        response = beta.decisions.create(model=config.DECISION_MODEL, input=input_data, questions=PNG_CHECK)
        return {
            "noul": response.answers["inscription"].noul,
            "choice": response.answers["route"].choice,
            "score": response.answers["legibility"].score,
            "confidence": response.answers["inscription"].confidence,
        }

    def managed():
        """Check client-side tools, streaming events and managed session continuation."""
        options = {
            "agent": config.ANTIGRAVITY_AGENT,
            "agent_config": {"type": "antigravity", "model": config.NEON, "max_total_tokens": 150_000},
            "tools": [ECHO],
        }
        events = list(beta.interactions.create(
            **options, environment="remote", input="Call measure with the label cedar.", stream=True,
        ))
        interaction = next(
            (value for event in reversed(events)
             if (value := getattr(event, "interaction", None)) is not None),
            None,
        )
        if interaction is None:
            raise ValueError("Stream did not expose an interaction for continuation")
        interaction = beta.interactions.get(interaction.id)
        replies = function_results(interaction.steps, managed=True)
        if interaction.status != "requires_action" or not replies:
            raise ValueError("Client-side function execution was not demonstrated")
        final = beta.interactions.create(
            **options, environment=interaction.environment_id,
            previous_interaction_id=interaction.id, input=replies,
        )
        return {"events": list(dict.fromkeys(event.event_type for event in events)), "final": final.output_text}

    checks = [("gemini.models", lambda: [model.name for model in client.models.list()])]
    checks += [
        (f"gemini.{model}", lambda model=model: structured(model, "Echo CEDAR 214 as your answer."))
        for model in (config.CARBON, config.NEON, config.HYDROGEN)
    ]
    checks.extend([
        ("gemini.pdf", lambda: structured(config.CARBON, [inline("text_pdf"), {"type": "text", "text": "What was the onset age?"}])),
        ("gemini.scanned_pdf", lambda: structured(config.CARBON, [inline("scanned_pdf"), {"type": "text", "text": "What does the image say?"}])),
        ("gemini.function_round_trip", tools_round_trip),
        ("decisions.text", lambda: decisions("The white test card is clearly marked CEDAR 214.")),
        ("decisions.png", lambda: decisions([inline("png")])),
        ("managed.function_round_trip", managed),
    ])
    return checks


def alphagenome_tests():
    """Construct AlphaGenome 2 and Atlas probes for a published human variant."""
    from alphagenome.atlas import atlas
    from alphagenome.data import genome
    from alphagenome.models.v2 import dna_client, variant_scorers

    if not config.ALPHAGENOME_API_KEY:
        raise PermissionError("AlphaGenome key missing")
    model = dna_client.create(config.ALPHAGENOME_API_KEY, timeout=8)
    atlas_client = atlas.create(config.ALPHAGENOME_API_KEY, timeout=8)
    example = genome.Variant(chromosome="chr22", position=36201698, reference_bases="A", alternate_bases="C")
    interval = example.reference_interval.resize(dna_client.SEQUENCE_LENGTH_1MB)

    def conditions():
        """Return reference-condition metadata relevant to the demo."""
        data = model.supported_conditions(dna_client.Organism.HOMO_SAPIENS)
        return json.loads(data[data.biosample_name.str.contains("brain|cortex|neuron|astrocyte|blood", case=False, na=False)].to_json(orient="records"))

    def score(condition):
        """Return a compact sample from the raw human splicing scores."""
        raw = model.score_variant(
            interval, example, condition=condition,
            variant_scorers=[variant_scorers.RECOMMENDED_VARIANT_SCORERS[name] for name in SCORERS],
        )
        data = variant_scorers.tidy_scores(raw, match_gene_strand=True)
        return json.loads(data[["output_type", "gene_name", "imputation_mode", "raw_score"]].head(20).to_json(orient="records"))

    return [
        ("alphagenome2.conditions", conditions),
        ("alphagenome2.brain", lambda: score(config.BRAIN_TISSUE)),
        ("alphagenome2.blood", lambda: score(config.BLOOD_TISSUE)),
        ("alphagenome2.prediction", lambda: sorted(vars(model.predict_variant(
            interval, example, condition=config.BRAIN_TISSUE, requested_outputs=[dna_client.OutputType.RNA_SEQ]
        )))),
        ("atlas.scorer_metadata", lambda: [str(item) for item in atlas_client.scorer_metadata()]),
        ("atlas.avi", lambda: {
            key: {"shape": list(value.shape), "obs": list(value.obs.columns), "var": list(value.var.columns)}
            for key, value in atlas_client.query_variants(
                [example], requested_scorers=["AVI"], max_workers=1, progress_bar=False
            ).items()
        }),
    ]


def main():
    """Run live probes once each and persist sanitized structured outcomes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=["all", "gemini", "alphagenome"], default="all")
    options = parser.parse_args()
    groups = {"gemini": gemini_tests, "alphagenome": alphagenome_tests}
    rows = []
    for group, build in groups.items():
        if options.group not in ("all", group):
            continue
        try:
            checks = build()
        except Exception as error:
            rows.append({"probe": group, "status": "blocked", "error_type": type(error).__name__})
            continue
        rows.extend(measure(name, action) for name, action in checks)
    out = Path(__file__).parent / "outputs" / f"{options.group}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"date": READ_DATE, "results": rows}, indent=2) + "\n")
    for row in rows:
        print(f"{row['probe']}: {row['status']}")
    return 0 if all(row["status"] == "ok" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
