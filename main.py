import os, subprocess, tempfile, requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="FFmpeg Stitch Server for @prayer_tube")

class StitchRequest(BaseModel):
    video_urls: List[str]
    audio_url: Optional[str] = None
    audio_base64: Optional[str] = None
    srt_content: Optional[str] = None
    output_filename: Optional[str] = "final_short.mp4"

def download_file(url: str, dest: str):
    r = requests.get(url, timeout=120, stream=True)
    r.raise_for_status()
    with open(dest, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

@app.post("/stitch")
async def stitch(req: StitchRequest):
    work_dir = tempfile.mkdtemp(prefix="stitch_")
    try:
        clip_paths = []
        for i, url in enumerate(req.video_urls):
            path = os.path.join(work_dir, f"clip_{i:02d}.mp4")
            download_file(url, path)
            clip_paths.append(path)
        concat_file = os.path.join(work_dir, "concat.txt")
        with open(concat_file, 'w') as f:
            for p in clip_paths:
                f.write(f"file '{p}'\n")
        silent_out = os.path.join(work_dir, "silent_combined.mp4")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_file, "-c:v", "libx264", "-preset", "fast",
            "-crf", "23", "-an", silent_out], check=True, capture_output=True)
        final_out = os.path.join(work_dir, "final_short.mp4")
        if req.audio_base64 or req.audio_url:
            audio_path = os.path.join(work_dir, "narration.mp3")
            if req.audio_base64:
                import base64
                with open(audio_path, 'wb') as f:
                    f.write(base64.b64decode(req.audio_base64))
            else:
                download_file(req.audio_url, audio_path)
            if req.srt_content:
                srt_path = os.path.join(work_dir, "subs.srt")
                with open(srt_path, 'w', encoding='utf-8') as f:
                    f.write(req.srt_content)
                subprocess.run(["ffmpeg", "-y", "-i", silent_out, "-i", audio_path,
                    "-vf", f"subtitles='{srt_path}':force_style='FontSize=18,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Alignment=2'",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", final_out],
                    check=True, capture_output=True)
            else:
                subprocess.run(["ffmpeg", "-y", "-i", silent_out, "-i", audio_path,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                    "-shortest", final_out], check=True, capture_output=True)
        else:
            os.rename(silent_out, final_out)
        return FileResponse(final_out, media_type="video/mp4", filename=req.output_filename)
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, detail=f"FFmpeg error: {e.stderr.decode()[-500:]}")
    except Exception as e:
        raise HTTPException(500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}
