# Smart Meeting Minutes - Restructured Project

Dự án đã được chia lại thành 3 phần riêng biệt:

## 🏗️ Cấu trúc dự án

```
final/
├── ai-service/           # AI Service (Python FastAPI)
├── backend-nestjs/       # Backend API (NestJS)
├── frontend-nextjs/      # Frontend (Next.js)
├── backend/              # Backend cũ (FastAPI) - có thể xóa
├── frontend/             # Frontend cũ (Vite React) - có thể xóa
└── README.md
```

## 🚀 Cách chạy dự án

### 1. AI Service (Python FastAPI)
```bash
cd ai-service
pip install -r requirements.txt
python main.py
```
- Chạy trên port: `8001`
- API endpoints: `/speech-to-text`, `/clean`, `/summarize`, `/diarize`, `/extract`, `/process-full`

### 2. Backend NestJS
```bash
cd backend-nestjs
npm install
npm run start:dev
```
- Chạy trên port: `3000`
- API endpoints: `/meeting/process`, `/meeting/speech-to-text`, etc.

### 3. Frontend Next.js
```bash
cd frontend-nextjs
npm install
npm run dev
```
- Chạy trên port: `3001`
- Giao diện web để upload file và xem kết quả

## 🔧 Cấu hình

### AI Service
Tạo file `.env` trong `ai-service/`:
```env
GOOGLE_API_KEY=your_google_api_key_here
SPEECHMATICS_API_KEY=your_speechmatics_api_key_here
```

### Backend NestJS
Tạo file `.env` trong `backend-nestjs/`:
```env
PORT=3000
AI_SERVICE_URL=http://localhost:8001
```

## 📋 API Endpoints

### AI Service (Port 8001)
- `POST /speech-to-text` - Chuyển đổi audio thành text
- `POST /clean` - Làm sạch text
- `POST /summarize` - Tóm tắt và cấu trúc hóa
- `POST /diarize` - Phân tách người nói
- `POST /extract` - Trích xuất action items và decisions
- `POST /process-full` - Xử lý toàn bộ pipeline

### Backend NestJS (Port 3000)
- `POST /meeting/process` - Xử lý file audio/transcript
- `POST /meeting/speech-to-text` - Chuyển đổi audio
- `POST /meeting/clean` - Làm sạch text
- `POST /meeting/summarize` - Tóm tắt
- `POST /meeting/diarize` - Phân tách người nói
- `POST /meeting/extract` - Trích xuất nội dung

## 🔄 Luồng hoạt động

1. **Frontend** (Next.js) nhận file từ user
2. **Backend** (NestJS) nhận request và gọi **AI Service** (Python)
3. **AI Service** xử lý file và trả về kết quả
4. **Backend** trả về kết quả cho **Frontend**
5. **Frontend** hiển thị kết quả và cho phép export

## 🛠️ Công nghệ sử dụng

### AI Service
- Python 3.8+
- FastAPI
- Google Generative AI (Gemini)
- Speechmatics API
- Pydantic

### Backend NestJS
- Node.js 18+
- NestJS
- TypeScript
- Axios
- Class Validator

### Frontend Next.js
- React 18+
- Next.js 15+
- TypeScript
- Tailwind CSS
- React Dropzone
- Lucide React

## 📝 Ghi chú

- Đảm bảo các API keys được cấu hình đúng trong file `.env`
- Các service cần được chạy theo thứ tự: AI Service → Backend → Frontend
