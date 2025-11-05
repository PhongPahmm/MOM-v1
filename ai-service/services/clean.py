import re
from typing import List

def clean_transcript(text: str) -> str:
	"""
	Clean and normalize transcript text with minimal information loss.
	Optimized for accuracy in meeting minutes extraction.
	"""
	if not text:
		return ""
	
	# ONLY remove true filler words that don't carry meaning
	# Be very conservative - when in doubt, keep the word
	filler_words = [
		# English fillers - only clear hesitations
		"uh", "um", "ah", "eh", "er", "hmm", "oh",
		"you know", "i mean", "kind of", "sort of", "like actually",
		# Vietnamese fillers - only clear hesitations
		"ừ", "ờ", "à", "ạ", "nhé", "nhá"
	]
	
	# Normalize whitespace first
	text = re.sub(r'\s+', ' ', text)
	text = text.strip()
	
	# Remove ONLY obvious filler phrases (case insensitive, word boundary aware)
	for filler in filler_words:
		# Use word boundaries to avoid partial matches
		pattern = r'\b' + re.escape(filler) + r'\b'
		text = re.sub(pattern, '', text, flags=re.IGNORECASE)
	
	# Clean up punctuation spacing (but preserve the punctuation itself)
	text = re.sub(r'\s*\.\s*', '. ', text)
	text = re.sub(r'\s*,\s*', ', ', text)
	text = re.sub(r'\s*;\s*', '; ', text)
	text = re.sub(r'\s*:\s*', ': ', text)
	text = re.sub(r'\s*\?\s*', '? ', text)
	text = re.sub(r'\s*!\s*', '! ', text)
	
	# Fix multiple spaces
	text = re.sub(r'\s+', ' ', text)
	
	# Remove spaces before punctuation at end of sentences
	text = re.sub(r'\s+([.!?])', r'\1', text)
	
	# Capitalize first letter of sentences
	sentences = re.split(r'([.!?])\s+', text)
	result = []
	for i, part in enumerate(sentences):
		if i % 2 == 0 and part:  # Text parts (not punctuation)
			result.append(part.strip().capitalize() if part.strip() else part)
		else:  # Punctuation
			result.append(part)
	text = ''.join(result)
	
	# Final cleanup
	text = re.sub(r'\s+', ' ', text)
	text = text.strip()
	
	# Ensure sentence ends with punctuation
	if text and not text[-1] in '.!?':
		text += '.'
	
	return text
