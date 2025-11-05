import re
from typing import List, Tuple

def diarize(text: str) -> List[Tuple[str, str]]:
	"""
	Speaker diarization based on text patterns.
	Optimized for accuracy in meeting minutes - preserves full context when no clear speakers.
	"""
	if not text:
		return []
	
	# Extended speaker indicators including department names and roles
	speaker_patterns = [
		# Explicit speaker labels
		r'(?:Speaker\s*\d+)',
		r'(?:Người\s+nói\s*\d+)',
		r'(?:Person\s*\d+)',
		r'(?:P\d+)',
		r'(?:S\d+)',
		# Titles with names
		r'(?:Mr\.?\s+[A-Z][a-z]+)',
		r'(?:Ms\.?\s+[A-Z][a-z]+)',
		r'(?:Mrs\.?\s+[A-Z][a-z]+)',
		r'(?:Dr\.?\s+[A-Z][a-z]+)',
		r'(?:Anh\s+[A-Z][a-z]+)',
		r'(?:Chị\s+[A-Z][a-z]+)',
		r'(?:Ông\s+[A-Z][a-z]+)',
		r'(?:Bà\s+[A-Z][a-z]+)',
		# Department/Role indicators (common in meetings)
		r'(?:HR)',
		r'(?:Finance)',
		r'(?:IT)',
		r'(?:Manager[s]?)',
		r'(?:Team Lead)',
		r'(?:Director)',
	]
	
	# Split text into potential speaker segments
	segments = []
	current_speaker = "Unknown"
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
	
	# CRITICAL: If no speaker patterns found, treat as SINGLE speaker
	# This is more accurate than randomly distributing - keeps context intact
	if not segments or (len(segments) == 1 and segments[0][0] == "Unknown"):
		# Return full text as single speaker
		# This preserves all context for extraction algorithms
		return [("Meeting Transcript", text)]
	
	return segments
