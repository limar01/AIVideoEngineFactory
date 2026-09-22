"""FFmpeg assembly (Sprint A): concat clips, concat narration, mux."""
import subprocess, os

def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)

def _concat(items, out):
    lst = out + ".list.txt"
    with open(lst, "w") as f:
        for c in items:
            f.write("file '%s'\n" % os.path.abspath(c))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])

def concat_videos(clips, out):
    _concat(clips, out)

def concat_audios(wavs, out):
    _concat(wavs, out)

def mux(video, audio, out):
    run(["ffmpeg", "-y", "-i", video, "-i", audio, "-c:v", "copy", "-c:a", "aac", "-shortest", out])

def probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path], capture_output=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return -1.0
