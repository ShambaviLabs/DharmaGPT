@echo off
cd /d "C:\Users\sahit\OneDrive\Projects\DharmaGPT\dharmagpt"
set PYTHONPATH=C:\Users\sahit\OneDrive\Projects\DharmaGPT\dharmagpt
python scripts\transcribe_audio_batch.py ^
  --input-dir "..\downloads\Sampoorna Ramayanam by Sri Chaganti Koteswara Rao Garu" ^
  --output-dir "..\downloads\clips_29s_full" ^
  --language-code te-IN ^
  --language-tag te ^
  --api-url "http://localhost:8001/api/v1/audio/transcribe" ^
  --segment-seconds 29 ^
  --chunk-delay 2.0
