# Submission checklist (the humans do these by hand)

Nothing here may be done by an agent: no submitting, no uploading, no posting, no repository settings.

## Before the 4:15 p.m. ET code freeze

- [ ] Run the live demo three times on the final build: two picks from the list and one Random. Check the picker, the PDF, the live events, the ranking, Reveal, the plot and Accept/Reject. Write down each investigation time.
- [ ] Read the README once, top to bottom, as a judge would. Check that the benchmark numbers match `bench/results/test/report.md`.
- [ ] Decide, together, when to push: everything has been local-only on purpose. Push once, after the last change, and check the commit list.
- [ ] Check that `.env` is ignored and untracked (`git ls-files .env` prints nothing), and that no key appears in the repository (`git log -p | grep -E 'AQ\.[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}'` prints nothing).
- [ ] Check that no commit message or file credits an AI coding assistant.

## Submit by 5:00 p.m. ET on Nov 21

- [ ] Open the repository logged out (private window) and confirm it is public, that the README renders, and that `bench/results/test/chart.png` shows.
- [ ] Record the 60-second video from `demo/VIDEO_SCRIPT.md` and upload it. Open the link logged out.
- [ ] Add every teammate (maximum four) on the submission page.
- [ ] Submit manually at https://cerebralvalley.ai/e/gemini-4-nyc/hackathon/submit. Choose a problem statement: **5 Sigma** (a real task, a baseline comparison and an honest failure analysis fits our evidence best). Name the models used: Gemini 4 Carbon, Neon, Hydrogen and Decision 1.
- [ ] Confirm that the submission is recorded on the event site.

## Before judging

- [ ] Run `python -m scripts.demo_check` with the live keys. All five checks must pass.
- [ ] Keep a recorded run on the laptop, labelled "recorded run", in case the venue Wi-Fi fails. Keep a phone hotspot ready.
- [ ] Charge the laptop, check the projector and the PDF display, and do not restart the laptop (the data folder holds the cached AlphaGenome results).
- [ ] Rehearse the 3-minute pitch in `demo/PITCH.md` with the run already streaming, and the Q&A answers.
