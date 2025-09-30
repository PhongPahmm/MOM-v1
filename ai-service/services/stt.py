from typing import Optional
import os
import json
import requests

from core.config import settings

async def transcribe_audio(file_path: str, language: Optional[str] = None) -> str:
    """
    Transcribe audio file using Speechmatics API (free plan available).
    """
    speechmatics_api_key = settings.speechmatics_api_key  # bạn cần set trong .env
    if not speechmatics_api_key:
        raise ValueError(
            "Speechmatics API key is not configured. Please set SPEECHMATICS_API_KEY in your environment "
            "variables or .env file. Get your API key from: https://portal.speechmatics.com/api-key"
        )

    try:
        # Step 1: Upload file
        url = "https://asr.api.speechmatics.com/v2/jobs/"
        headers = {"Authorization": f"Bearer {speechmatics_api_key}"}

        # Map language codes for Speechmatics
        speechmatics_lang = language or "en"
        if speechmatics_lang == "vi":
            speechmatics_lang = "vi"  # Speechmatics supports Vietnamese

        config_data = {
            "type": "transcription",
            "transcription_config": {
                "language": speechmatics_lang,
                "operating_point": "standard"
            }
        }

        with open(file_path, "rb") as f:
            files = {"data_file": f}
            data = {"config": json.dumps(config_data)}
            response = requests.post(url, headers=headers, data=data, files=files)

        if response.status_code != 201:
            raise ValueError(f"Speechmatics job creation failed: {response.status_code} - {response.text}")

        job_id = response.json().get("id")
        if not job_id:
            raise ValueError(f"Speechmatics did not return job id: {response.text}")

        # Step 2: Poll for result
        result_url = f"{url}{job_id}/transcript?format=txt"
        max_attempts = 60  # poll tối đa 60 lần (60 giây)
        
        for attempt in range(max_attempts):
            import asyncio
            await asyncio.sleep(1)  # Đợi 1 giây trước khi poll
            
            r = requests.get(result_url, headers=headers)
            if r.status_code == 200:
                transcript = r.text.strip()
                if transcript:
                    return transcript
                else:
                    # Nếu response trống, tiếp tục polling
                    continue
            elif r.status_code == 404:
                # job chưa xong, tiếp tục polling
                continue
            elif r.status_code == 400:
                # Bad request, có thể job failed
                raise ValueError(f"Speechmatics job failed: {r.text}")
            else:
                raise ValueError(f"Speechmatics result error: {r.status_code} - {r.text}")

        raise TimeoutError(f"Speechmatics transcription timed out after {max_attempts} seconds")

    except Exception as e:
        raise ValueError(f"Speechmatics transcription failed: {e}")
