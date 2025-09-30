import re
from typing import List, Tuple

def diarize(text: str) -> List[Tuple[str, str]]:
	"""
	Simple speaker diarization based on text patterns.
	In a real implementation, this would use audio-based speaker recognition.
	"""
	if not text:
		return []
	
	# Common speaker indicators in transcripts
	speaker_patterns = [
		r'(?:Speaker\s*\d+)',
		r'(?:Người\s+nói\s*\d+)',
		r'(?:Person\s*\d+)',
		r'(?:P\d+)',
		r'(?:S\d+)',
		r'(?:Mr\.?\s+\w+)',
		r'(?:Ms\.?\s+\w+)',
		r'(?:Mrs\.?\s+\w+)',
		r'(?:Anh\s+\w+)',
		r'(?:Chị\s+\w+)',
		r'(?:Ông\s+\w+)',
		r'(?:Bà\s+\w+)',
	]
	
	# Split text into potential speaker segments
	segments = []
	current_speaker = "Speaker 1"
	current_text = ""
	
	lines = text.split('\n')
	
	for line in lines:
		line = line.strip()
		if not line:
			continue
			
		# Check if line contains speaker information
		speaker_found = None
		for pattern in speaker_patterns:
			match = re.search(pattern, line, re.IGNORECASE)
			if match:
				speaker_found = match.group(0)
				break
		
		if speaker_found:
			# Save previous segment
			if current_text.strip():
				segments.append((current_speaker, current_text.strip()))
			
			# Start new segment
			current_speaker = speaker_found
			# Remove speaker label from text
			current_text = re.sub(rf'^{re.escape(speaker_found)}:\s*', '', line)
			current_text = re.sub(rf'^{re.escape(speaker_found)}\s*', '', current_text)
		else:
			# Continue current segment
			if current_text:
				current_text += " " + line
			else:
				current_text = line
	
	# Add the last segment
	if current_text.strip():
		segments.append((current_speaker, current_text.strip()))
	
	# If no speaker patterns found, treat as single speaker
	if not segments:
		# Try to split by sentences and assign to different speakers
		sentences = re.split(r'[.!?]+', text)
		sentences = [s.strip() for s in sentences if s.strip()]
		
		if len(sentences) <= 1:
			return [("Speaker 1", text)]
		
		# Distribute sentences among speakers
		speakers = ["Speaker 1", "Speaker 2", "Speaker 3"]
		segments = []
		for i, sentence in enumerate(sentences):
			speaker = speakers[i % len(speakers)]
			segments.append((speaker, sentence))
	
	return segments
