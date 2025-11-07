# Dataset Generation và Training Scripts

## 1. Generate Dataset (`generate_dataset.py`)

Script để generate dataset từ transcripts và lưu vào file JSONL format cho fine-tuning.

### Cách sử dụng:

```bash
# Generate dataset với local LLM
python scripts/generate_dataset.py --output meeting_dataset.jsonl

# Load transcripts từ file
python scripts/generate_dataset.py --transcripts-file transcripts.txt --output dataset.jsonl
```

**Lưu ý**: Script chỉ sử dụng local LLM model đang chạy (từ `core.config`). Không cần API key, hoàn toàn offline.

### Input format:

**File transcripts.txt** (một transcript mỗi dòng):
```
Good morning everyone. HR will draft the remote work policy by October 15.
Finance needs to finalize the Q4 budget by October 20.
Sarah to coordinate with external vendors by end of week.
```

**Hoặc JSON array:**
```json
[
  "Transcript 1...",
  "Transcript 2...",
  "Transcript 3..."
]
```

### Output format:

File JSONL với format fine-tuning:
```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "transcript..."},
    {"role": "assistant", "content": "{\"action_items\": [...], \"decisions\": [...]}"}
  ]
}
```

## 2. Load Dataset to Vector DB (`load_dataset_to_vector_db.py`)

Script để load dataset từ JSONL file và thêm vào vector database để sử dụng cho vector-based extraction.

### Cách sử dụng:

```bash
# Load dataset vào vector database
python scripts/load_dataset_to_vector_db.py --dataset meeting_dataset.jsonl
```

Script sẽ:
1. Đọc từng record trong dataset
2. Extract transcript, action_items, và decisions
3. Thêm vào vector database
4. Rebuild vector index
5. Save vector database

## Workflow hoàn chỉnh:

```bash
# Bước 1: Generate dataset từ transcripts
python scripts/generate_dataset.py --output meeting_dataset.jsonl

# Bước 2: Load dataset vào vector database
python scripts/load_dataset_to_vector_db.py --dataset meeting_dataset.jsonl

# Bước 3: Restart AI service để sử dụng vector database mới
# Vector database sẽ được auto-load khi service start
```

## Lưu ý:

1. **Local LLM (Bắt buộc)**: 
   - Script chỉ sử dụng local LLM model từ `core.config` (thường là `google/gemma-2b-it`)
   - Model sẽ được load tự động khi chạy script
   - Không cần API key, hoàn toàn offline
   - Phù hợp cho việc generate dataset với model đang chạy local
   - Nếu model cần authentication, xem `HUGGINGFACE_SETUP.md`

2. **Vector Database**: 
   - Sẽ được lưu vào `vector_db.pkl` trong thư mục hiện tại
   - Auto-load khi service start

3. **Dataset Format**: 
   - Phải theo format fine-tuning với `messages` array
   - Output là JSONL file (một JSON object mỗi dòng)

## Tùy chỉnh:

- Thay đổi `SYSTEM_PROMPT` trong `generate_dataset.py` để customize extraction
- Thay đổi `SAMPLE_TRANSCRIPTS` để thêm transcripts mẫu
- Adjust `vector_similarity_threshold` trong `core.config.py` để control similarity matching

