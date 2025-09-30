import re
from typing import List

def clean_transcript(text: str) -> str:
	"""Clean and normalize transcript text by removing filler words and improving formatting."""
	if not text:
		return ""
	
	# Common filler words in Vietnamese and English
	filler_words = [
		"uh", "um", "ah", "eh", "er", "hmm", "oh", "well", "you know", "like", "so", "actually",
		"basically", "literally", "obviously", "clearly", "definitely", "probably", "maybe",
		"kind of", "sort of", "i mean", "right", "okay", "ok", "yeah", "yes", "no",
		# Vietnamese fillers
		"ừ", "ờ", "à", "ạ", "thì", "là", "và", "có thể", "chắc là", "có lẽ", "được rồi",
		"đúng rồi", "thôi", "này", "ấy", "nhé", "nhá", "đó", "đây", "kia", "nọ"
	]
	
	# Normalize whitespace
	text = re.sub(r'\s+', ' ', text)
	text = text.strip()
	
	# Remove filler words (case insensitive)
	words = text.split()
	cleaned_words = []
	
	for word in words:
		# Remove punctuation for comparison
		clean_word = re.sub(r'[^\w]', '', word.lower())
		if clean_word not in filler_words and len(clean_word) > 0:
			cleaned_words.append(word)
	
	# Join back and clean up punctuation
	result = ' '.join(cleaned_words)
	
	# Fix sentence endings
	result = re.sub(r'\s*\.\s*', '. ', result)
	result = re.sub(r'\s*,\s*', ', ', result)
	result = re.sub(r'\s*;\s*', '; ', result)
	result = re.sub(r'\s*:\s*', ': ', result)
	
	# Fix multiple spaces
	result = re.sub(r'\s+', ' ', result)
	
	# Capitalize first letter of sentences
	sentences = result.split('. ')
	sentences = [sentence.strip().capitalize() if sentence.strip() else sentence for sentence in sentences]
	result = '. '.join(sentences)
	
	return result.strip()
