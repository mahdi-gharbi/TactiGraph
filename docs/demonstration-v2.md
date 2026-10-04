# Three-minute local demonstration

The recording shows the local application using real WSL data and the configured
Groq interpreter. It is a feature walkthrough, with independent review still pending.
The video and full screenshots stay in private `output/demo-v2/`; they are not
bundled with the public image or a reviewed public showcase.

| Time | What to show | Explanation |
| --- | --- | --- |
| 0:00–0:20 | League, Arsenal–Liverpool match, source | Select the context before interpreting the question |
| 0:20–1:05 | FR question; 45–60 vs 60–75; xG explanation | Groq interprets; Python calculates; BM25 cites a definition |
| 1:05–1:35 | Open a numerical evidence link | Show the definition, event count and source references |
| 1:35–2:10 | EN question on the same match | Same bounded analysis with verified English templates |
| 2:10–2:40 | “after minute 60” | Ask for complete windows, show no unsupported numerical report |
| 2:40–3:00 | Delivery and evaluation status | Local delivery; independent evaluation and public access pending |

## Re-record

Start the built local application with its Groq configuration on port 8004. Run:

```powershell
npm.cmd --prefix frontend run demo:record -- http://127.0.0.1:8004
```

The script makes two real question calls and one provider-free clarification. It
does not intercept responses or replace evidence. Failures stop the recording.
Keep the original video metadata and API traces for auditing. No numerical accuracy
claim or human approval follows from a successful recording.

The README screenshot uses the explicitly invented CI fixture and simulated
interpreter; its role is to show the interface. It is separate from this private
recording and from real-provider evaluation.
