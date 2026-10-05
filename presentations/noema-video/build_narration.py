import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = Path("/Users/federicovargas/Desktop/Screen Recording 2026-10-03 at 12.15.59\u202fAM.mov")
SEGMENTS = [
    (
        8,
        "Welcome to Noema, our banking assistant prototype for the Factored Data Hackathon. This walkthrough follows a customer from account questions to a credit inquiry and a request for human support.",
    ),
    (
        25,
        "Step one: establish the customer context. Sandra introduces herself, and the interface loads her demo profile. This is a demonstration identity flow; it does not establish production banking authentication.",
    ),
    (
        45,
        "On the right, the step-by-step panel displays rules, observations, and evidence. It distinguishes achieved checks from missing and pending items, giving reviewers a view of the system behind the conversation.",
    ),
    (
        69,
        "Step two: ask about the customer profile. Sandra requests a financial summary. This broad request is not resolved in the recording, so she follows up by naming the specific account details she wants.",
    ),
    (
        95,
        "The assistant returns a recorded balance. Notice that the request also included income and active products, but the response covers only the balance. This is a partial answer, and a useful improvement target.",
    ),
    (
        115,
        "Step three: ask focused account questions. The balance is repeated consistently, followed by an estimated monthly income. For a clearer banking experience, the income response should also identify its currency.",
    ),
    (
        138,
        "Step four: explore credit eligibility. Sandra asks about credit cards. Noema requests an amount and currency before continuing. The intended design separates the conversation from the eligibility policy.",
    ),
    (
        164,
        "Sandra enters a ten-thousand-dollar credit card request. As the response arrives, review the proposed terms. The recording alone does not prove that those terms match a completed, customer-specific policy decision.",
    ),
    (
        184,
        "The answer switches to Spanish. Sandra asks to continue in English. This shows why preserving the preferred language throughout the workflow matters to the customer experience.",
    ),
    (
        207,
        "Step five: review the response and request the next action. The assistant describes a credit limit and rate, then asks whether Sandra wants to proceed. An offer in chat is not confirmation that an application has been created.",
    ),
    (
        229,
        "Step six: request human support. Noema says it cannot proceed and offers an advisor. The clip ends with a referral message; a completed handoff still needs a visible case reference and confirmation.",
    ),
]


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def stamp(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


clips = []
captions = []
script = [
    "# NOEMA Guided Demo",
    "",
    "Voice: macOS Zoe (Enhanced), synthetic English narration. Not the ChatGPT voice.",
    "",
    "This narration describes the recorded prototype, including visible limitations.",
    "",
]
for index, (start, words) in enumerate(SEGMENTS):
    clip = ROOT / f"narration-{index:02}.aiff"
    run(["say", "-v", "Zoe (Enhanced)", "-r", "155", "-o", str(clip), words])
    duration = float(
        run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(clip),
            ]
        ).stdout
    )
    limit = SEGMENTS[index + 1][0] if index + 1 < len(SEGMENTS) else 249.51
    if start + duration > limit:
        raise RuntimeError(f"Narration {index} overlaps next scene: {duration}")
    clips.append((clip, start, duration))
    # Sentence-level cues are proportional to spoken length, not word-aligned.
    sentences = [s.strip() + "." for s in words.split(".") if s.strip()]
    total = sum(len(s) for s in sentences)
    cursor = start
    for sentence in sentences:
        end = cursor + duration * len(sentence) / total
        captions.append(f"{len(captions) + 1}\n{stamp(cursor)} --> {stamp(end)}\n{sentence}\n")
        cursor = end
    script.extend([f"## {stamp(start)}", "", words, ""])

(ROOT / "NOEMA_Narration.md").write_text("\n".join(script))
(ROOT / "NOEMA_Captions.srt").write_text("\n".join(captions))
(ROOT / "timing.json").write_text(
    json.dumps([{"start": s, "duration": d} for _, s, d in clips], indent=2)
)
args = ["ffmpeg", "-y", "-v", "error"]
for clip, _, _ in clips:
    args += ["-i", str(clip)]
filters = [
    f"[{i}:a]adelay={round(start * 1000)}:all=1[a{i}]" for i, (_, start, _) in enumerate(clips)
]
filters.append(
    "".join(f"[a{i}]" for i in range(len(clips)))
    + f"amix=inputs={len(clips)}:normalize=0,apad,atrim=duration=249.51,loudnorm=I=-16:TP=-1.5:LRA=11[out]"
)
run(
    args
    + [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[out]",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(ROOT / "NOEMA_Narration.m4a"),
    ]
)
print("Narration and captions generated; rendering video.", flush=True)
vf = "scale=1600:-2,zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
run(
    [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(SOURCE),
        "-i",
        str(ROOT / "NOEMA_Narration.m4a"),
        "-i",
        str(ROOT / "NOEMA_Captions.srt"),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-map",
        "2:0",
        "-vf",
        vf,
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-c:a",
        "copy",
        "-c:s",
        "mov_text",
        "-metadata:s:a:0",
        "language=eng",
        "-metadata:s:a:0",
        "title=English guided narration - synthetic voice",
        "-metadata:s:s:0",
        "language=eng",
        "-t",
        "249.51",
        "-movflags",
        "+faststart",
        str(ROOT / "NOEMA_Guided_Demo.mp4"),
    ]
)
print("Complete: NOEMA_Guided_Demo.mp4", flush=True)
