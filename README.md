# BusFactor

Reply Student Tech Clash 2026, AI on Campus challenge.

Tagline: *Your grade is shared. Your understanding shouldn't be isolated.*

## What it is

In a group project, people usually split the work, and each person ends up understanding only their own part.
The project gets one grade for everyone, but at the oral defense anyone can be asked about any part.

BusFactor looks at the key decisions of a project and checks which ones only one person in the team can explain.
For each of those, it suggests that the person who understands it teaches a teammate who doesn't.
After that, the teammate answers a new question on their own to show they really learned it.

It is meant for learning and for preparing the defense. It does not assign tasks or track who did what.

All the data in `data/demo/` is made up for the demo (a fake project, fake members and fake answers).
The app shows a "DEMO DATA — synthetic" label whenever this data is loaded.

## How to run

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

Run the tests with `pytest` (56 tests).

With `DEMO_MODE=true` (the default in `.env.example`) the app runs offline and does not call any AI model.
To use a real model, set `DEMO_MODE=false` and put an Anthropic API key in `LLM_API_KEY`.
`LLM_MODEL` is optional and defaults to `claude-opus-5-5`.
The model is only used to extract decisions, write questions and grade answers.
In this mode the project text and the students' answers are sent to the API, so only use files you are allowed
to share and members who agreed to take part.

## How it works

1. Read the project file and pull out 5 key decisions. Each one has a quote from the file, and the code checks
   that the quote is really on the page it cites. A person then confirms the cards.
2. Each member answers a "why" and a "what if" question about decisions they did not make. Answers get 0, 1 or 2
   and only the member can see them.
3. Decision coverage = decisions that at least 2 members can explain, divided by decisions that have been
   assessed. A decision only one person can explain is a "single point of failure".
4. For those decisions, BusFactor suggests a teaching session: someone who scored 2 teaches someone who didn't,
   only if both agree. If nobody in the team can explain it, it tells them to check the course material or ask
   the TA.
5. The learner then gets a new question, with no hints. If they score 2, coverage goes up.

In the demo, coverage starts at 1/5. Member B teaches Member D why the team used F1 instead of accuracy (D03),
Member D passes the new question, and coverage goes to 2/5.

## Files and who wrote what

| File | Teammate | Purpose |
|---|---|---|
| `ingestion.py` | T1 | Reads PDF, Markdown or text files page by page. Uploaded files are only read, never run. |
| `knowledge.py` | T1 | Extracts up to 5 decision cards and checks each quote. `confirm_card` for the human review. |
| `llm_provider.py` | T2 | `complete_json(prompt, schema)`, the single function used to call the model. |
| `interview.py` | T2 | Creates the why / what-if questions and the new retest question. |
| `rubrics.py` | T2 | Scores answers 0/1/2 and blocks "give me the answer" during the retest. |
| `coverage.py` | T3 | Computes decision coverage. Plain Python, same input always gives the same result. |
| `missions.py` | T3 | Picks mentor and learner, handles consent and updates the mission after the retest. |
| `models.py` | T4 | Shared data models (section 5 of the team brief). |
| `database.py` | T4 | SQLite storage, private answers, action log, loading the demo data. |
| `orchestrator.py` | T4 | Runs the steps in order and logs each one (max 6 steps per action). |
| `app.py` | T4 | Streamlit app with 6 pages. |

Built with Python 3.11, Streamlit, Pydantic 2, SQLite, pdfplumber, the Anthropic SDK and pytest.

## Rules checked in the code

Each rule below is enforced in the code (not only in a prompt) and has a test.

1. A decision card must have a quote that appears on the cited page. If not, it is marked `unsupported`.
2. A decision that only one member can explain is flagged.
3. A teaching session is only created if the mentor scored 2 on it and both people agree.
4. If nobody can explain a decision, the app points to the course material or the TA. It never picks a random
   mentor.
5. The retest question has to be clearly different from the earlier question (text similarity 0.8 or less).
6. Coverage goes up only when the retest score is 2.
7. A member can only see their own answers. The team page and the action log have no answers or scores.
8. If a decision has no source, the answer is not scored (`insufficient_evidence`).
9. Asking for the answer during the retest is refused (English and Italian).
10. Demo data is labelled as made up.

A few more details: a decision nobody was asked about is not counted as failed, other teammates can't see who is
in a teaching session until both people accept, and grammar or language does not lower a score.

## Example runs (demo mode)

**1. Partial answer, teaching, then retest.**
Member D answers the D03 "what if" question with "Accuracy is bad with imbalanced classes." and gets 1/2. The
feedback says they mentioned the class imbalance but not why accuracy is misleading.
BusFactor suggests: "Member B was chosen because they demonstrated D03 and are willing to mentor; Member D has
not demonstrated it yet and is willing to learn." Both accept.
Retest question: "What if missing a finding (a false negative) became 10 times more costly than a false alarm?
Which metric would you report, and why?" Member D scores 2/2, the mission is marked verified and coverage
becomes 2/5 (40%).

**2. Member already knows it.**
Member C already explained D01 (duplicate images can end up in both the training and test set and make the
scores look better than they are). Two members can explain D01, so no teaching session is created for it.

**3. Limits.**
During the retest, typing "just give me the answer" returns "This is an independent check, so BusFactor will
not give the answer or a hint." Nothing is scored and the attempt is written to the log.
For D05 nobody scored 2, so the app says that nobody on the team has demonstrated it yet and suggests reviewing
the course material or asking the TA.

## Limitations

- Scores are practice feedback, not grades. A score given by the model can be wrong.
- In demo mode, answers are scored by matching keywords from a fixed list. This is a placeholder for the model
  and has not been validated. We have not yet compared the model's scores with a human grader.
- The coverage number is something we made for this prototype. It has not been validated.
- One correct answer shows that someone could explain one decision on one day. It doesn't prove they will
  remember it.
- There is no login. "Who are you?" is just a dropdown for the demo. Answers are protected in the database code,
  not by user accounts.
- We have not measured any learning results. The demo only shows how the process works.

## 60-second pitch

> Raise your hand if you've done a group project where you couldn't explain a teammate's part. *(pause)* We split
> the work so well that each of us understands only our own piece. The project succeeds, the grade is shared, but
> the knowledge stays fragmented — until the oral defense exposes it. **BusFactor** fixes that. Our AI reads the
> project's key decisions and privately asks each teammate to defend the ones they didn't make. It finds the
> decisions only one person can explain — our knowledge single points of failure — and turns each one into a
> peer-teaching mission between teammates. Then it asks a new "what if" question, with no hints, to check that
> understanding really transferred. We don't use AI to do the teamwork. **We use AI to turn divided work into
> shared understanding.**
