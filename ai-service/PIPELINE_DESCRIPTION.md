# Mô Tả Chi Tiết Pipeline Xử Lý Meeting Minutes

## Tổng Quan

Pipeline `/process-full` là hệ thống xử lý tự động để chuyển đổi audio hoặc transcript của cuộc họp thành meeting minutes có cấu trúc, bao gồm tóm tắt, phân loại người nói, và trích xuất action items cùng decisions. Hệ thống được thiết kế với khả năng xử lý song song và cơ chế fallback đa tầng để đảm bảo độ tin cậy cao.

---

## Bước 1: Thu Thập Dữ Liệu Đầu Vào (Input Acquisition)

Pipeline bắt đầu bằng việc nhận đầu vào từ client, có thể là file audio hoặc file transcript văn bản. Nếu là file audio, hệ thống sẽ tạo một thư mục tạm thời sử dụng module `tempfile` của Python để lưu trữ file audio tạm thời. File audio được đọc từ request và ghi vào thư mục tạm với tên file gốc hoặc tên mặc định "audio_input" nếu không có tên file. Sau đó, hệ thống gọi hàm `transcribe_audio()` để chuyển đổi audio thành văn bản.

Hàm `transcribe_audio()` sử dụng mô hình Whisper của OpenAI, một công cụ speech-to-text mã nguồn mở chạy local trên server. Mô hình Whisper được load một lần duy nhất khi lần đầu tiên được sử dụng và được cache trong biến global `_whisper_model` để tránh phải load lại nhiều lần, giúp tiết kiệm thời gian và tài nguyên. Kích thước mô hình mặc định là "base" (có thể cấu hình trong settings), cân bằng giữa độ chính xác và tốc độ xử lý. Quá trình transcription nhận vào đường dẫn file audio và mã ngôn ngữ (mặc định là "vi" cho tiếng Việt), sau đó Whisper sẽ phân tích audio và trả về văn bản transcript thô. Nếu đầu vào là file transcript văn bản, hệ thống sẽ đọc trực tiếp nội dung file và decode sang UTF-8, bỏ qua bước transcription. Cuối cùng, hệ thống kiểm tra xem có nội dung văn bản hay không, nếu không có sẽ trả về lỗi 400 Bad Request.

---

## Bước 2: Làm Sạch Và Chuẩn Hóa Văn Bản (Text Cleaning)

Sau khi có được văn bản transcript thô, hệ thống cần làm sạch và chuẩn hóa văn bản này trước khi xử lý tiếp. Bước này được thực hiện bằng hàm `clean_transcript()` thông qua `asyncio.to_thread()` để chạy trong thread pool riêng, tránh block event loop của FastAPI. Hàm `clean_transcript()` sử dụng cơ chế fallback ba tầng để đảm bảo luôn có kết quả.

Tầng đầu tiên là sử dụng Large Language Model (LLM) từ OpenAI, cụ thể là mô hình GPT-4o-mini. Hệ thống tạo một prompt chi tiết với các quy tắc làm sạch cụ thể, bao gồm việc loại bỏ các từ filler không có nghĩa như "uh", "um", "ừ", "ờ", chuẩn hóa khoảng trắng và dấu câu, đồng thời giữ nguyên tất cả nội dung có nghĩa như tên người, ngày tháng, số liệu và thuật ngữ kỹ thuật. Prompt được gửi đến OpenAI API với temperature thấp (0.1) để đảm bảo kết quả nhất quán và chính xác. Nếu OpenAI API thành công, văn bản đã làm sạch được trả về sau khi loại bỏ các markdown code blocks nếu có.

Nếu OpenAI API thất bại do lỗi xác thực, hết quota, hoặc các lỗi API khác, hệ thống tự động chuyển sang tầng thứ hai là sử dụng Google Gemini API. Gemini được cấu hình với API key từ environment variables hoặc file `.env`. Prompt tương tự được gửi đến Gemini và kết quả được xử lý giống như với OpenAI.

Nếu cả hai LLM đều thất bại, hệ thống chuyển sang tầng thứ ba là phương pháp pattern-based cleaning sử dụng regular expressions. Phương pháp này loại bỏ các từ filler bằng cách tìm kiếm pattern cụ thể với word boundaries, chuẩn hóa khoảng trắng bằng regex `\s+`, và sửa định dạng dấu câu. Mặc dù không thông minh bằng LLM, phương pháp này đảm bảo hệ thống luôn có thể xử lý được văn bản và hoạt động nhanh chóng mà không cần kết nối mạng.

Sau khi có văn bản đã làm sạch, hệ thống chia văn bản thành các câu bằng cách tách theo dấu chấm, loại bỏ các khoảng trắng thừa và các câu rỗng. Danh sách các câu này sẽ được sử dụng cho các bước xử lý tiếp theo.

---

## Bước 3: Xử Lý Song Song - Tóm Tắt Và Phân Loại Người Nói (Parallel Processing)

Bước thứ ba là bước quan trọng nhất trong việc tối ưu hiệu suất của pipeline. Thay vì xử lý tuần tự, hệ thống chạy song song hai tác vụ độc lập là tóm tắt (summarize) và phân loại người nói (diarization) vì chúng không phụ thuộc vào nhau. Tác vụ tóm tắt nhận vào danh sách các câu đã được chia nhỏ từ bước trước, trong khi tác vụ phân loại người nói nhận vào toàn bộ văn bản đã làm sạch.

Cả hai tác vụ được khởi chạy đồng thời bằng cách sử dụng `asyncio.to_thread()` để chạy các hàm CPU-bound trong thread pool riêng, sau đó sử dụng `asyncio.gather()` với tham số `return_exceptions=True` để chờ cả hai hoàn thành. Tham số `return_exceptions=True` là điểm quan trọng trong thiết kế này vì nó cho phép hệ thống không bị dừng lại khi một trong hai tác vụ gặp lỗi. Thay vì raise exception ngay lập tức và hủy tác vụ còn lại, `asyncio.gather()` sẽ wrap exception vào kết quả trả về, cho phép tác vụ còn lại tiếp tục chạy đến khi hoàn thành.

Tác vụ tóm tắt (`summarize()`) sử dụng LLM để trích xuất thông tin có cấu trúc từ transcript. Hàm này tạo một prompt chi tiết với system prompt định nghĩa schema JSON bao gồm các trường như title (tiêu đề cuộc họp), date và time (ngày giờ), attendants (danh sách người tham gia), project_name (tên dự án), customer (tên khách hàng), table_of_content (mục lục các chủ đề chính), và main_content (nội dung tóm tắt chính từ 200-500 từ). Prompt được gửi đến OpenAI GPT-4o-mini với max_tokens là 4096 để đảm bảo không bị cắt response. Nếu OpenAI thất bại, hệ thống tự động fallback sang Gemini với cùng prompt và logic. Kết quả trả về là một JSON object chứa tất cả thông tin đã được cấu trúc hóa. Hệ thống có cơ chế retry tối đa 2 lần nếu JSON response bị lỗi parse, và có logic đặc biệt để sửa các JSON bị cắt cụt bằng cách đếm dấu ngoặc kép và đóng các string chưa hoàn chỉnh.

Tác vụ phân loại người nói (`diarize()`) sử dụng LLM để phân tích transcript và xác định các người nói khác nhau. Hàm này tạo prompt với yêu cầu trả về JSON array, mỗi phần tử chứa thông tin về speaker (người nói) và text (nội dung họ nói). LLM sẽ phân tích transcript dựa trên các manh mối như tên người được đề cập, chức danh, phong cách nói, và ngữ cảnh để xác định các speaker khác nhau. Nếu không thể xác định được tên cụ thể, hệ thống sẽ sử dụng các identifier như "Speaker 1", "Speaker 2" hoặc các vai trò như "Manager", "IT Team". Kết quả được chuyển đổi thành danh sách các tuple `(speaker, text)` để dễ dàng sử dụng trong các bước tiếp theo. Nếu LLM thất bại, hệ thống fallback sang phương pháp pattern-based sử dụng regex để tìm các pattern như "Speaker 1", "Mr. Smith", "Anh Minh", hoặc các từ khóa chỉ vai trò như "HR", "Finance", "IT". Nếu vẫn không tìm được, hệ thống sẽ chia transcript thành các chunks và gán speaker giả định.

Sau khi cả hai tác vụ hoàn thành (hoặc một trong hai gặp lỗi), hệ thống kiểm tra kết quả trả về. Nếu một trong hai kết quả là Exception object (do `return_exceptions=True`), hệ thống sẽ log lỗi và gán giá trị mặc định: empty dictionary `{}` cho summary và empty list `[]` cho segments. Điều này cho phép pipeline tiếp tục chạy ngay cả khi một trong hai tác vụ thất bại, đảm bảo tính khả dụng của hệ thống. Hệ thống cũng kiểm tra các giá trị `None` và chuyển đổi chúng thành giá trị mặc định tương ứng để tránh lỗi trong các bước tiếp theo.

---

## Bước 4: Trích Xuất Action Items Và Decisions (Extraction)

Bước cuối cùng là trích xuất các action items (nhiệm vụ) và decisions (quyết định) từ transcript. Hàm `extract_actions_and_decisions()` nhận vào danh sách các câu đã được chia nhỏ và dữ liệu phân loại người nói từ bước trước. Dữ liệu phân loại người nói được sử dụng để xác định owner (người chịu trách nhiệm) của các action items và decisions, mặc dù không bắt buộc - nếu không có dữ liệu này, owner sẽ là `None`.

Hàm này sử dụng LLM với prompt được tối ưu hóa để trích xuất thông tin có cấu trúc. Prompt yêu cầu LLM trả về JSON với hai mảng: `action_items` chứa các object có các trường description (mô tả nhiệm vụ), owner (người chịu trách nhiệm), due_date (hạn chót), và priority (mức độ ưu tiên); và `decisions` chứa các object có các trường text (nội dung quyết định) và owner. LLM được hướng dẫn tìm kiếm các từ khóa như "will", "needs to", "to do", "by [date]" cho action items và "decided", "agreed", "approved" cho decisions.

Hệ thống có cơ chế retry thông minh với tối đa 3 lần thử. Nếu LLM trả về JSON không hợp lệ, hệ thống sẽ cải thiện prompt bằng cách thêm hướng dẫn rõ ràng hơn về format JSON và yêu cầu không có trailing commas hoặc comments. Sau mỗi lần thử thất bại, prompt được cập nhật với thông báo về lỗi trước đó và yêu cầu LLM trả về JSON hợp lệ. Hàm `_try_parse_json()` được sử dụng để parse JSON, có khả năng loại bỏ markdown code blocks và extract JSON từ text nếu bị wrap.

Sau khi parse thành công, hệ thống validate và chuyển đổi dữ liệu thành các object `ActionItem` và `Decision` theo schema đã định nghĩa. Các item không có description hoặc text sẽ bị loại bỏ. Cuối cùng, hệ thống giới hạn số lượng kết quả trả về tối đa 25 items cho mỗi loại để tránh response quá lớn.

---

## Bước 5: Tổng Hợp Và Trả Về Kết Quả (Response Assembly)

Sau khi tất cả các bước xử lý hoàn thành, hệ thống tổng hợp tất cả kết quả thành một JSON response duy nhất. Response bao gồm transcript đã làm sạch, structured summary (có thể là empty dictionary nếu summarize thất bại), danh sách action items với đầy đủ thông tin description, owner, due_date, và priority, danh sách decisions với text và owner, và dữ liệu diarization dưới dạng danh sách các object chứa speaker và text. Tất cả các giá trị `None` được xử lý cẩn thận để đảm bảo JSON response luôn hợp lệ.

Hệ thống có global exception handler để bắt tất cả các exception không được xử lý, đảm bảo luôn trả về response với CORS headers để client có thể nhận được kết quả ngay cả khi có lỗi xảy ra. Exception handler log chi tiết lỗi bao gồm type và traceback để hỗ trợ debugging.

---

## Luồng Xử Lý Cuộc Họp Online Với LiveKit (LiveKit Meeting Flow)

Hệ thống sử dụng LiveKit - một nền tảng WebRTC mã nguồn mở - để tổ chức và quản lý cuộc họp trực tuyến. LiveKit được tích hợp trực tiếp vào ứng dụng thông qua SDK `livekit-client` và `@livekit/components-react`, cho phép người dùng tổ chức cuộc họp, chia sẻ màn hình, và tự động ghi âm audio từ tất cả người tham gia để xử lý thành meeting minutes.

### Kiến Trúc LiveKit Trong Hệ Thống

Hệ thống sử dụng LiveKit Server được cấu hình thông qua các biến môi trường `LIVEKIT_URL`, `LIVEKIT_API_KEY`, và `LIVEKIT_API_SECRET`. Mỗi dự án (project) có một phòng họp riêng với tên phòng là `project-{projectId}`, cho phép các thành viên của dự án tham gia và tổ chức cuộc họp. Hệ thống có ba API routes chính để quản lý cuộc họp: `/api/realtime/token` để lấy access token, `/api/realtime/status` để kiểm tra trạng thái cuộc họp, và `/api/realtime/end` để kết thúc cuộc họp.

### Bước 1: Khởi Tạo Và Tham Gia Cuộc Họp

Khi người dùng muốn bắt đầu hoặc tham gia một cuộc họp, họ click vào nút "Start Meeting" hoặc "Join Meeting" trên giao diện. Hệ thống sẽ gọi API `/api/realtime/token` với `projectId` để lấy LiveKit access token. API này thực hiện các bước xác thực và kiểm tra quyền truy cập: đầu tiên, nó kiểm tra người dùng đã đăng nhập thông qua cookie `access_token`, sau đó lấy thông tin người dùng và dự án từ backend API. Hệ thống kiểm tra xem người dùng có phải là thành viên của dự án hay không, nếu không sẽ trả về lỗi 403 Forbidden.

Sau khi xác thực thành công, hệ thống tạo một LiveKit `AccessToken` với `identity` duy nhất (định dạng `{userId}-{randomUUID}`), `name` của người tham gia, và metadata chứa thông tin về dự án và phòng họp. Token được cấp quyền `roomJoin`, `canPublish`, và `canSubscribe` để người dùng có thể tham gia phòng, publish audio/video tracks của mình, và subscribe tracks từ người khác. API cũng kiểm tra các participants đang hoạt động trong phòng để xác định host (người đầu tiên join) và trả về thông tin này cùng với token.

Frontend nhận được token và thông tin kết nối, sau đó sử dụng component `LiveKitRoom` từ `@livekit/components-react` để kết nối vào phòng LiveKit. Component này nhận vào `serverUrl` (LIVEKIT_URL), `token` (access token vừa nhận được), và các options như `adaptiveStream` và `dynacast` để tối ưu chất lượng stream dựa trên băng thông. Khi kết nối thành công, event `onConnected` được trigger và hệ thống xác định vai trò của người dùng (host hoặc participant) dựa trên `isHostCandidate` flag từ token response.

### Bước 2: Tự Động Ghi Âm Audio Từ Cuộc Họp

Một tính năng quan trọng của hệ thống là tự động ghi âm audio từ tất cả người tham gia trong cuộc họp. Khi host (người đầu tiên join phòng) kết nối thành công, hệ thống tự động bắt đầu ghi âm thông qua custom hook `useRoomAudioRecorder`. Hook này sử dụng Web Audio API để capture và mix audio từ tất cả audio tracks trong phòng LiveKit.

Quá trình ghi âm bắt đầu bằng việc tạo một `MediaStream` rỗng để chứa tất cả audio tracks. Hook lắng nghe các events từ LiveKit room như `TrackSubscribed`, `TrackUnsubscribed`, `LocalTrackPublished`, `LocalTrackUnpublished`, `ParticipantConnected`, và `ParticipantDisconnected` để tự động thêm hoặc xóa audio tracks khi có người tham gia hoặc rời khỏi cuộc họp. Mỗi khi có một audio track mới (từ local participant hoặc remote participant), hook sẽ thêm track đó vào MediaStream để đảm bảo tất cả audio đều được ghi lại.

Khi bắt đầu recording, hook tạo một `AudioContext` với sample rate mặc định của trình duyệt (thường là 48000 Hz). Sau đó, hook tạo một `GainNode` (mixer node) để mix tất cả audio tracks lại với nhau. Mỗi audio track được chuyển đổi thành một `MediaStreamAudioSourceNode` và kết nối vào mixer node. Mixer node được kết nối với một `ScriptProcessorNode` (với buffer size 4096 samples) để xử lý audio data theo từng chunk. ScriptProcessorNode sử dụng callback `onaudioprocess` để capture audio samples và lưu vào memory dưới dạng `Float32Array` cho mỗi channel (stereo recording với 2 channels).

Audio pipeline được thiết lập như sau: các source nodes (từ audio tracks) → mixer node → processor node → silent gain node (gain = 0 để không phát ra loa) → destination. Điều này đảm bảo audio được capture và xử lý mà không gây feedback hoặc echo cho người tham gia. Hook cũng theo dõi thời gian bắt đầu recording và tổng số samples đã ghi được để tính toán duration sau này.

### Bước 3: Xử Lý Và Export Audio Recording

Khi host click "End Meeting" hoặc disconnect khỏi phòng, hook `useRoomAudioRecorder` tự động dừng recording và xử lý audio data đã ghi được. Quá trình này bao gồm việc disconnect tất cả source nodes, processor node, và mixer node khỏi AudioContext để giải phóng tài nguyên. Sau đó, hook merge tất cả audio chunks đã ghi được thành các mảng `Float32Array` hoàn chỉnh cho mỗi channel.

Audio data được encode thành định dạng WAV sử dụng hàm `encodeWavFromChannels`. Hàm này tạo một WAV file header với các thông tin như sample rate, số channels (stereo), bit depth (16-bit), và kích thước data. Audio samples được convert từ Float32 (-1.0 đến 1.0) sang Int16 (16-bit PCM) và ghi vào ArrayBuffer. Kết quả là một `Blob` object với MIME type `audio/wav` chứa toàn bộ audio recording của cuộc họp.

Recording được trả về thông qua callback `onRecordingReady` với thông tin bao gồm `blob` (WAV file), `mimeType`, `durationMs` (thời lượng tính bằng milliseconds), và `startedAt` (timestamp khi bắt đầu recording). Component `RealtimeMeeting` nhận được recording và tạo một object URL từ blob để hiển thị cho người dùng. Người dùng có thể click nút "Export Audio" để tải file WAV về máy tính với tên file có định dạng `project-{projectId}-{timestamp}.wav`.

### Bước 4: Xử Lý Audio Recording Qua AI Pipeline

Sau khi export audio file từ LiveKit recording, người dùng có thể upload file này lên hệ thống để xử lý thành meeting minutes. File audio được gửi đến AI Service thông qua endpoint `/process-full` như đã mô tả trong các bước trước. Tuy nhiên, audio từ LiveKit có một số đặc điểm đặc biệt: đây là audio đã được mix từ nhiều người tham gia, có chất lượng tốt do được capture trực tiếp từ WebRTC stream, và không có nhiễu từ microphone như các recording thông thường.

Khi audio file được upload và gửi đến AI Service, pipeline xử lý như sau: Bước 1 (STT) sử dụng Whisper để transcribe audio thành văn bản. Whisper xử lý audio đã mix này tốt hơn so với audio có nhiều người nói cùng lúc vì audio đã được mix và cân bằng. Bước 2 (Clean) làm sạch transcript, loại bỏ các từ filler và chuẩn hóa văn bản. Bước 3 (Parallel Processing) chạy song song summarize và diarize. Điều thú vị là diarization trong trường hợp này có thể khó khăn hơn vì audio đã được mix, nhưng LLM vẫn có thể phân tích ngữ cảnh và phong cách nói để xác định các speaker khác nhau. Bước 4 (Extract) trích xuất action items và decisions. Bước 5 (Response Assembly) tổng hợp tất cả kết quả.

### Quản Lý Trạng Thái Cuộc Họp

Hệ thống có cơ chế quản lý trạng thái cuộc họp thông qua API `/api/realtime/status`. API này sử dụng `RoomServiceClient` từ LiveKit SDK để kiểm tra xem phòng họp có đang active hay không bằng cách list participants trong phòng. Frontend gọi API này mỗi 5 giây để cập nhật trạng thái cuộc họp và hiển thị cho người dùng biết có cuộc họp đang diễn ra hay không.

Khi host kết thúc cuộc họp, hệ thống gửi một data message qua LiveKit room với type `meeting-status` và status `ended` để thông báo cho tất cả participants. Các participants nhận được message này sẽ tự động disconnect và reset recording state. Host cũng gọi API `/api/realtime/end` để đóng phòng trên LiveKit server, đảm bảo phòng được cleanup đúng cách.

### Tối Ưu Hóa Và Đặc Điểm Kỹ Thuật

Hệ thống có một số tối ưu hóa đặc biệt cho LiveKit integration. Đầu tiên, hệ thống sử dụng `adaptiveStream` và `dynacast` options để tự động điều chỉnh chất lượng stream dựa trên băng thông và khả năng xử lý của client. Điều này giúp đảm bảo cuộc họp mượt mà ngay cả khi băng thông không ổn định.

Thứ hai, hệ thống chỉ cho phép host (người đầu tiên join) bắt đầu và kết thúc recording. Điều này tránh conflict khi nhiều người cùng cố gắng control recording và đảm bảo chỉ có một bản recording duy nhất cho mỗi cuộc họp. Recording tự động bắt đầu khi host connect và tự động dừng khi host disconnect hoặc end meeting.

Thứ ba, hệ thống xử lý động các participants join/leave trong quá trình recording. Hook `useRoomAudioRecorder` tự động thêm audio tracks mới khi có người join và remove tracks khi có người leave, đảm bảo recording luôn bao gồm tất cả audio trong cuộc họp. Điều này được thực hiện thông qua việc tạo và connect source nodes mới vào mixer trong khi đang recording.

Cuối cùng, hệ thống sử dụng Web Audio API với ScriptProcessorNode để xử lý audio ở mức thấp, cho phép kiểm soát hoàn toàn quá trình mixing và encoding. Mặc dù ScriptProcessorNode đã deprecated trong favor của AudioWorklet, nó vẫn được hỗ trợ rộng rãi và phù hợp cho use case này. Audio được encode thành WAV format để đảm bảo chất lượng tốt nhất và tương thích với Whisper model.

---

## Tích Hợp Với Trello (Trello Integration)

Hệ thống tích hợp với Trello để tự động tạo các Trello cards từ action items được trích xuất từ meeting minutes. Tính năng này cho phép người dùng đồng bộ các nhiệm vụ từ cuộc họp trực tiếp vào Trello board để theo dõi tiến độ công việc một cách hiệu quả.

### Kiến Trúc Tích Hợp Trello

Tích hợp Trello được xây dựng trên Trello REST API và sử dụng OAuth 1.0a để xác thực người dùng. Hệ thống lưu trữ thông tin kết nối Trello của mỗi người dùng trong database thông qua bảng `trello_integration`, bao gồm `access_token`, `token_secret`, `member_id`, `member_username`, và `member_full_name`. Mỗi người dùng chỉ có thể kết nối một tài khoản Trello duy nhất, và thông tin này được liên kết với `user_id` trong hệ thống.

### Bước 1: Xác Thực OAuth Với Trello

Khi người dùng muốn kết nối tài khoản Trello của họ với hệ thống, họ click vào nút "Connect Trello" trong giao diện. Hệ thống sẽ gọi API `/api/trello/oauth/request-token` để khởi tạo quá trình OAuth. API này sử dụng thư viện `oauth-1.0a` để tạo OAuth signature với `TRELLO_API_KEY` và `TRELLO_API_SECRET` được cấu hình trong environment variables.

API tạo một request token bằng cách gửi POST request đến `https://trello.com/1/OAuthGetRequestToken` với OAuth authorization header được ký bằng HMAC-SHA1. Request bao gồm callback URL là `/api/trello/oauth/callback` để Trello redirect về sau khi người dùng authorize. Khi nhận được request token và token secret từ Trello, hệ thống lưu chúng vào HTTP-only cookies với tên `trello_oauth_token` và `trello_oauth_secret`, có thời gian sống 10 phút. Hệ thống cũng lưu return URL (URL mà người dùng sẽ được redirect về sau khi kết nối thành công) vào cookie `trello_return_to`.

Sau đó, hệ thống redirect người dùng đến Trello authorization page tại `https://trello.com/1/OAuthAuthorizeToken` với các tham số như `oauth_token` (request token), `name` (tên ứng dụng), `scope` (read,write), và `expiration` (never). Trên trang này, người dùng sẽ thấy thông tin về quyền mà ứng dụng yêu cầu và có thể chấp nhận hoặc từ chối.

### Bước 2: Xử Lý OAuth Callback

Sau khi người dùng chấp nhận trên Trello, Trello sẽ redirect về callback URL `/api/trello/oauth/callback` với các tham số `oauth_token` và `oauth_verifier`. API callback này thực hiện các bước sau: đầu tiên, nó kiểm tra request token từ cookie có khớp với `oauth_token` trong URL hay không để đảm bảo tính bảo mật và tránh CSRF attacks.

Sau đó, API sử dụng request token và token secret từ cookie cùng với `oauth_verifier` để tạo OAuth signature và gửi POST request đến `https://trello.com/1/OAuthGetAccessToken` để đổi lấy access token và access token secret. Đây là các credentials cuối cùng được sử dụng để gọi Trello API thay cho người dùng.

Khi nhận được access token, API gọi Trello API `/members/me` để lấy thông tin profile của người dùng bao gồm `id`, `username`, và `fullName`. Thông tin này cùng với access token và token secret được gửi đến backend API `/api/core/v1/integration/trello` để lưu vào database. Backend sử dụng Prisma để upsert record vào bảng `trello_integration` với `user_id` của người dùng hiện tại.

Sau khi lưu thành công, hệ thống redirect người dùng về return URL ban đầu với query parameter `trelloConnected=1` để frontend biết kết nối đã thành công. Nếu có lỗi xảy ra, hệ thống redirect về với `trelloConnected=0` và `trelloError` chứa thông báo lỗi. Tất cả cookies OAuth được xóa sau khi xử lý xong để đảm bảo bảo mật.

### Bước 3: Kiểm Tra Trạng Thái Kết Nối

Hệ thống cung cấp API `/api/core/v1/integration/trello/status` để kiểm tra xem người dùng đã kết nối Trello hay chưa. API này kiểm tra trong database xem có record `trello_integration` cho user hiện tại hay không. Nếu có, API trả về `connected: true` cùng với thông tin member (id, username, fullName) và thời gian kết nối (`connectedAt`). Nếu không có, API trả về `connected: false`.

Frontend sử dụng API này để hiển thị trạng thái kết nối trong giao diện. Khi người dùng mở modal export Trello, hệ thống tự động gọi API này để kiểm tra trạng thái. Nếu đã kết nối, hệ thống sẽ load danh sách boards và lists từ Trello. Nếu chưa kết nối, hệ thống hiển thị nút "Connect Trello" để người dùng có thể bắt đầu quá trình OAuth.

### Bước 4: Lấy Danh Sách Boards Và Lists

Khi người dùng đã kết nối Trello và muốn export action items, hệ thống cần cho phép người dùng chọn board và list đích. API `/api/trello/boards` được gọi để lấy danh sách tất cả boards mà người dùng có quyền truy cập. API này sử dụng access token đã lưu trong database để gọi Trello API `/members/me/boards` với các tham số `key` (TRELLO_API_KEY), `token` (access token của người dùng), `fields` (name,url), và `filter` (open để chỉ lấy các board đang mở).

Kết quả trả về là một mảng các `TrelloBoard` object chứa `id`, `name`, và `url`. Frontend hiển thị danh sách này trong dropdown để người dùng chọn board. Khi người dùng chọn một board, hệ thống tự động gọi API `/api/trello/lists` với `boardId` để lấy danh sách các lists trong board đó.

API `/api/trello/lists` gọi Trello API `/boards/{boardId}/lists` với access token của người dùng để lấy tất cả lists trong board. Kết quả trả về là một mảng các `TrelloList` object chứa `id` và `name`. Frontend hiển thị danh sách này trong dropdown thứ hai để người dùng chọn list đích cho các cards sẽ được tạo.

### Bước 5: Export Action Items Sang Trello Cards

Sau khi người dùng đã chọn board và list đích, họ có thể click nút "Export" để tạo Trello cards từ các action items trong meeting minutes. Hệ thống gọi API `/api/trello/export` với payload chứa `meetingTitle`, `actionItems` (mảng các action items với description, assignee, và dueDate), và `listId` (ID của list đích đã chọn).

API export thực hiện các bước sau: đầu tiên, nó validate request body để đảm bảo có đầy đủ thông tin cần thiết. Sau đó, nó làm sạch action items bằng cách loại bỏ các items không có description hoặc description rỗng. Nếu không còn action item hợp lệ nào, API trả về lỗi 400 Bad Request.

Tiếp theo, API lấy access token của người dùng từ database thông qua `fetchTrelloCredential()`. Hàm này gọi backend API `/api/core/v1/integration/trello/credential` với access token của ứng dụng để lấy Trello credentials đã lưu. Nếu người dùng chưa kết nối Trello, API trả về lỗi 404 Not Found.

Với mỗi action item hợp lệ, API tạo một Trello card bằng cách gọi Trello API `POST /cards` với các tham số sau: `key` (TRELLO_API_KEY), `token` (access token của người dùng), `idList` (ID của list đích), `name` (tên card - được giới hạn tối đa 256 ký tự), `desc` (mô tả card - được giới hạn tối đa 16384 ký tự), `pos` (vị trí card - "bottom" để thêm vào cuối list), và `due` (due date nếu có, được convert sang ISO format).

Tên card được tạo theo format: nếu action item có assignee, tên sẽ là `{assignee} – {description}`, nếu không có assignee thì chỉ là `{description}`. Mô tả card bao gồm các thông tin: "Meeting: {meetingTitle}", "Assignee: {assignee}" (nếu có), và "Due date: {dueDate}" (nếu có), mỗi thông tin trên một dòng riêng.

API xử lý từng action item tuần tự và đếm số lượng cards đã tạo thành công. Nếu có lỗi xảy ra khi tạo một card, lỗi đó được log nhưng không dừng quá trình xử lý các cards còn lại. Sau khi xử lý xong tất cả action items, API trả về response với `cardsCreated` là số lượng cards đã tạo thành công.

### Bước 6: Ngắt Kết Nối Trello

Người dùng có thể ngắt kết nối Trello bất cứ lúc nào bằng cách click nút "Disconnect" trong giao diện. Hệ thống gọi API `DELETE /api/core/v1/integration/trello` để xóa record `trello_integration` khỏi database. Sau khi disconnect thành công, tất cả thông tin kết nối Trello của người dùng được xóa và họ sẽ cần kết nối lại nếu muốn sử dụng tính năng export Trello trong tương lai.

### Tối Ưu Hóa Và Bảo Mật

Hệ thống có một số biện pháp bảo mật và tối ưu hóa cho tích hợp Trello. Đầu tiên, tất cả OAuth tokens được lưu trong HTTP-only cookies để tránh XSS attacks. Cookies được set với `sameSite: "lax"` và `secure: true` trong môi trường production để đảm bảo chỉ được gửi qua HTTPS.

Thứ hai, access token và token secret được mã hóa và lưu an toàn trong database. Mỗi người dùng chỉ có thể truy cập credentials Trello của chính họ thông qua authentication middleware của ứng dụng. API endpoints đều yêu cầu authentication token để đảm bảo chỉ người dùng đã đăng nhập mới có thể sử dụng.

Thứ ba, hệ thống validate và sanitize tất cả input từ người dùng trước khi gửi đến Trello API. Tên card và mô tả được giới hạn độ dài theo giới hạn của Trello API để tránh lỗi. Due date được validate và convert sang đúng format ISO trước khi gửi.

Cuối cùng, hệ thống xử lý lỗi một cách graceful. Nếu Trello API trả về lỗi, hệ thống log chi tiết lỗi và trả về thông báo lỗi rõ ràng cho người dùng. Nếu một card không thể tạo được, hệ thống tiếp tục tạo các cards còn lại thay vì dừng toàn bộ quá trình, đảm bảo người dùng nhận được càng nhiều cards càng tốt.

---

## Tính Năng Highlight (Text Highlighting Feature)

Hệ thống cung cấp tính năng highlight tự động để làm nổi bật các thông tin quan trọng trong transcript và meeting minutes, giúp người dùng dễ dàng nhận diện và theo dõi các thông tin như tên người, ngày tháng, thời gian, và các từ khóa quan trọng.

### Kiến Trúc Highlight

Tính năng highlight được triển khai ở cả hai frontend applications với mức độ phức tạp khác nhau. Trong `synapse-meeting-notes`, hệ thống sử dụng một engine highlight phức tạp với nhiều loại patterns và xử lý overlap, trong khi `frontend-nextjs` sử dụng một implementation đơn giản hơn với regex patterns cơ bản. Cả hai đều hoạt động trên client-side để đảm bảo hiệu suất và không cần gọi API.

### Bước 1: Xây Dựng Patterns Cho Highlight

Hệ thống định nghĩa nhiều loại patterns khác nhau để nhận diện các loại thông tin cần highlight. Đầu tiên, hệ thống xây dựng pattern cho tên người từ danh sách speakers trong meeting. Hàm `buildNameRegex()` nhận vào một object chứa thông tin speakers và tạo một regex pattern bao gồm cả tên đầy đủ và tên đầu tiên của mỗi speaker. Các tên được escape các ký tự đặc biệt trong regex và được sắp xếp theo độ dài giảm dần để ưu tiên match các tên dài hơn trước, đảm bảo độ chính xác khi có tên ngắn là substring của tên dài.

Tiếp theo, hệ thống định nghĩa các patterns cho ngày tháng với nhiều định dạng khác nhau. `datePatterns` bao gồm các format như ISO 8601 (2025-11-06T14:30:00Z), RFC 2822 (Mon, 06 Nov 2025 14:30:00 +0500), định dạng Mỹ (MM/DD/YYYY), định dạng châu Âu (DD/MM/YYYY), định dạng với tên tháng đầy đủ (November 6, 2025), định dạng tiếng Việt (ngày DD tháng MM năm YYYY), và nhiều biến thể khác. Mỗi pattern được thiết kế để bắt các format phổ biến nhất trong meeting transcripts.

Hệ thống cũng định nghĩa patterns cho thời gian (`timePatterns`) bao gồm format 12 giờ với AM/PM (10:30 AM, 2:45 PM), format 24 giờ (14:30:00), format với timezone (14:30:00+05:30), và các biến thể khác. Patterns cho tháng (`monthPatterns`) bao gồm tên tháng đầy đủ tiếng Anh (January, February), tên viết tắt (Jan, Feb), tên tháng tiếng Việt (tháng một, tháng Giêng), và các pattern với giới từ (in January, of January). Patterns cho năm (`yearPatterns`) bao gồm năm 4 chữ số (2025), năm với text (year 2025, năm 2025), năm với AD/BC (2025 AD, 500 BC), và các biến thể khác.

Ngoài ra, hệ thống còn định nghĩa patterns cho số thứ tự ngày trong tháng (`ordinalDayPatterns`) bao gồm số thứ tự bằng chữ tiếng Anh (first, second, third), số thứ tự bằng chữ tiếng Việt (một, hai, ba), số thứ tự với suffix (1st, 2nd, 3rd), và các pattern với giới từ (on the 1st, by 2nd, đến 1st). Patterns cho số (`numberPatterns`) bao gồm số thập phân (3.14), số với dấu phẩy phân cách hàng nghìn (1,000), số với phần trăm (50%), và số với đơn vị tiền tệ ($100, 100 USD).

### Bước 2: Thu Thập Highlights Từ Text

Hàm `highlightText()` thực hiện việc scan toàn bộ text và thu thập tất cả các matches từ các patterns đã định nghĩa. Quá trình này được thực hiện theo thứ tự ưu tiên: đầu tiên là tên người (names), sau đó là ngày tháng (dates), tiếp theo là tháng (months), năm (years), số thứ tự ngày (ordinal days), và cuối cùng là số (numbers).

Với mỗi pattern, hệ thống sử dụng `exec()` method của regex để tìm tất cả các matches trong text. Mỗi match được lưu vào một mảng `highlights` với thông tin về vị trí bắt đầu (`start`), vị trí kết thúc (`end`), loại highlight (`type`), và nội dung được match (`content`). Trước khi thêm một highlight mới, hệ thống kiểm tra xem nó có overlap với các highlights đã có cùng loại hay không để tránh duplicate highlights.

Đối với các patterns phức tạp như date patterns, hệ thống sử dụng negative lookahead để đảm bảo không highlight tháng hoặc năm nếu chúng đã là phần của một date pattern đầy đủ. Ví dụ, nếu text chứa "November 6, 2025", hệ thống sẽ chỉ highlight toàn bộ date này một lần thay vì highlight riêng "November", "6", và "2025" riêng biệt.

### Bước 3: Xử Lý Overlap Và Priority

Sau khi thu thập tất cả highlights, hệ thống sắp xếp chúng theo priority và độ dài. Priority được định nghĩa như sau: name có priority cao nhất (0), tiếp theo là date (1), ordinalDay (2), month (3), year (4), và number có priority thấp nhất (5). Điều này đảm bảo rằng khi có overlap, highlight có priority cao hơn sẽ được giữ lại.

Sau khi sắp xếp theo priority, hệ thống sắp xếp lại theo độ dài (dài trước) để ưu tiên các pattern dài hơn khi loại bỏ overlaps. Ví dụ, nếu có một date pattern "November 6, 2025" và một month pattern "November" overlap với nhau, hệ thống sẽ giữ lại date pattern vì nó dài hơn và có nhiều thông tin hơn.

Tiếp theo, hệ thống loại bỏ các overlaps bằng cách duyệt qua mảng highlights đã sắp xếp và chỉ giữ lại những highlight không overlap với các highlight đã được thêm vào mảng `filtered`. Một highlight được coi là overlap nếu vị trí của nó không hoàn toàn nằm ngoài vị trí của highlight khác (tức là `!(h.end <= f.start || h.start >= f.end)`).

Cuối cùng, hệ thống validate các highlights để đảm bảo chúng hợp lệ: `start >= 0`, `end > start`, `start < text.length`, và `end <= text.length`. Điều này đảm bảo không có highlight nào vượt quá giới hạn của text và không làm mất text gốc.

### Bước 4: Render Highlights Với React Components

Sau khi có danh sách highlights hợp lệ, hệ thống render chúng thành React components. Quá trình này được thực hiện bằng cách duyệt qua text từ đầu đến cuối và tạo các React nodes tương ứng.

Với mỗi highlight, hệ thống thêm phần text trước highlight (nếu có) vào mảng output, sau đó tạo một `<span>` element với className tương ứng với loại highlight. ClassName được xác định dựa trên `type` của highlight: `namePill` cho tên (màu xanh dương), `datePill` cho ngày tháng (màu tím), `timePill` cho thời gian (màu teal), `monthPill` cho tháng (màu hồng), `yearPill` cho năm (màu indigo), `numberPill` cho số (màu vàng), và `ordinalDayPill` cho số thứ tự ngày (màu cyan).

Mỗi `<span>` element được tạo với `key` duy nhất dựa trên type, start, và end để React có thể track và update chính xác. Nội dung text bên trong span là text gốc từ vị trí start đến end trong text gốc, đảm bảo không có thay đổi nào về nội dung, chỉ thêm styling để highlight.

Sau khi xử lý tất cả highlights, hệ thống thêm phần text còn lại sau highlight cuối cùng vào output. Điều này đảm bảo toàn bộ text gốc được render, không có phần nào bị mất. Nếu không có highlights nào hoặc có lỗi xảy ra, hàm `highlightTextSafe()` sẽ trả về text gốc để đảm bảo luôn có nội dung hiển thị.

### Bước 5: Hiển Thị Trong Meeting Transcript

Trong component `MeetingTranscript`, hàm `highlightTextSafe()` được gọi cho mỗi dòng transcript. Component này nhận vào một mảng `lines` chứa các `TranscriptLine` object với thông tin về speaker, text, actionItem (nếu có), và time (nếu có).

Với mỗi line, component hiển thị speaker name trong một pill màu xanh dương, sau đó là dấu hai chấm, và tiếp theo là text đã được highlight. Nếu line có `actionItem`, nó được hiển thị trong một pill màu đỏ. Nếu line có `time`, nó được hiển thị trong một pill màu xanh lá.

Tất cả các pills sử dụng Tailwind CSS classes với màu nền nhạt và màu chữ đậm để tạo contrast tốt và dễ đọc. Các pills được thiết kế với `rounded-md`, `px-2`, `py-0.5`, và `text-xs` để có kích thước nhỏ gọn và không làm gián đoạn flow đọc.

### Tối Ưu Hóa Và Xử Lý Lỗi

Hệ thống có một số tối ưu hóa và biện pháp xử lý lỗi. Đầu tiên, regex patterns cho names được memoize bằng `useMemo()` để tránh tạo lại pattern mỗi lần component re-render. Điều này cải thiện hiệu suất đáng kể khi có nhiều lines trong transcript.

Thứ hai, hàm `highlightTextSafe()` được wrap trong try-catch để đảm bảo không bao giờ làm crash component. Nếu có lỗi xảy ra trong quá trình highlight, hàm sẽ log lỗi và trả về text gốc, đảm bảo người dùng vẫn có thể đọc được nội dung.

Thứ ba, hệ thống xử lý các edge cases như text rỗng, text không hợp lệ, và highlights không hợp lệ một cách graceful. Tất cả các validation được thực hiện trước khi render để đảm bảo không có lỗi runtime.

Cuối cùng, hệ thống sử dụng một thuật toán hiệu quả để xử lý overlaps và priority, đảm bảo kết quả highlight chính xác và nhất quán. Thuật toán này được tối ưu để xử lý text dài với nhiều highlights mà không làm giảm hiệu suất.

### Implementation Đơn Giản Trong Frontend-NextJS

Trong `frontend-nextjs`, hệ thống sử dụng một implementation đơn giản hơn với hàm `highlightKeywords()`. Hàm này sử dụng một mảng các patterns đơn giản và thay thế các matches bằng HTML `<mark>` tags với các className tương ứng. Các patterns bao gồm time patterns (10:45 AM), date patterns (December 1st, 2025 và DD/MM/YYYY), name patterns (capitalized words), và task keywords (finalize, prepare, create, etc.).

Kết quả được render bằng `dangerouslySetInnerHTML` để hiển thị HTML đã được highlight. Mặc dù đơn giản hơn, implementation này vẫn cung cấp đủ chức năng để highlight các thông tin quan trọng trong meeting minutes và phù hợp với use case của ứng dụng này.

---

## Tính Năng Export PDF Và Word (PDF and Word Export Feature)

Hệ thống cung cấp tính năng export meeting minutes ra định dạng PDF và Word (DOC/DOCX) để người dùng có thể lưu trữ, chia sẻ, và in ấn các báo cáo cuộc họp một cách dễ dàng. Tính năng này cho phép xuất toàn bộ nội dung meeting minutes bao gồm thông tin cuộc họp, danh sách người tham gia, agenda, summary, decisions, và action items.

### Kiến Trúc Export

Tính năng export được triển khai ở cả hai frontend applications với các phương pháp khác nhau. Trong `synapse-meeting-notes`, hệ thống sử dụng browser print dialog để export PDF và tạo Word document từ HTML. Trong `frontend-nextjs`, hệ thống có thể sử dụng thư viện jsPDF và html2canvas (đã được cài đặt trong dependencies) để tạo PDF programmatically, mặc dù implementation hiện tại chỉ export HTML. Cả hai đều hoạt động trên client-side để đảm bảo privacy và không cần gửi dữ liệu lên server.

### Bước 1: Xây Dựng HTML Content Cho Export

Trước khi export, hệ thống cần tạo HTML content từ dữ liệu meeting minutes. Hàm `buildExportHtml()` trong `synapse-meeting-notes` hoặc `generateHTMLContent()` trong `frontend-nextjs` được gọi để tạo một HTML document hoàn chỉnh với tất cả thông tin cần thiết.

Quá trình này bắt đầu bằng việc sanitize tất cả text input để tránh XSS attacks và đảm bảo HTML hợp lệ. Hàm `safe()` được sử dụng để escape các ký tự đặc biệt như `&`, `<`, `>`, và convert newlines thành `<br/>` tags. Điều này đảm bảo nội dung được hiển thị đúng cách và không làm hỏng cấu trúc HTML.

Tiếp theo, hệ thống xây dựng HTML structure với các sections chính: header chứa title và metadata (date, time, minute ID), section Attendees với danh sách người tham gia và vai trò của họ, section Agenda với nội dung agenda, section Meeting Summary với tóm tắt cuộc họp, section Key Decisions với các quyết định quan trọng, và section Action Items với bảng chứa description, assignee, và due date.

HTML được tạo với embedded CSS styles để đảm bảo formatting nhất quán khi export. Styles bao gồm font family (Arial, Helvetica, sans-serif), font sizes cho headings, table styles với borders và padding, và spacing cho các sections. Styles được thiết kế để tối ưu cho cả màn hình và in ấn, với các màu sắc và contrast phù hợp.

### Bước 2: Export PDF

Trong `synapse-meeting-notes`, hàm `exportPdf()` thực hiện export PDF bằng cách sử dụng browser print dialog. Đầu tiên, hàm gọi `buildExportHtml()` để tạo HTML content. Sau đó, nó mở một cửa sổ mới bằng `window.open()` với target `_blank` để mở trong tab mới.

HTML content được write vào document của cửa sổ mới bằng `w.document.write(html)` và `w.document.close()`. Sau khi document được load, hệ thống đợi 300ms để đảm bảo content đã được render đầy đủ, sau đó gọi `w.focus()` để focus vào cửa sổ và `w.print()` để mở print dialog của browser.

Người dùng có thể chọn "Save as PDF" trong print dialog để lưu file PDF. Phương pháp này tận dụng khả năng print-to-PDF của browser, đảm bảo chất lượng tốt và tương thích với tất cả các browser hiện đại. Tuy nhiên, phương pháp này phụ thuộc vào browser print dialog và không thể tự động tạo file PDF mà không có tương tác từ người dùng.

Trong `frontend-nextjs`, mặc dù có thư viện jsPDF và html2canvas trong dependencies, implementation hiện tại chỉ export HTML file. Hàm `exportToPDF()` tạo một Blob từ HTML content với MIME type `text/html`, sau đó tạo một download link và trigger download. File được lưu với tên `meeting-minutes-{currentDate}.html`. Để implement PDF export thực sự, hệ thống có thể sử dụng html2canvas để capture HTML element thành canvas, sau đó sử dụng jsPDF để convert canvas thành PDF file.

### Bước 3: Export Word Document

Hàm `downloadWord()` trong `synapse-meeting-notes` thực hiện export Word document bằng cách tạo một Blob từ HTML content với MIME type `application/msword;charset=utf-8`. MIME type này cho phép Microsoft Word và các ứng dụng khác nhận diện file như một Word document.

Đầu tiên, hàm gọi `buildExportHtml()` để tạo HTML content. Sau đó, nó tạo một Blob object từ HTML string với MIME type `application/msword`. Blob này được convert thành URL bằng `URL.createObjectURL()` để có thể sử dụng như một download link.

Tiếp theo, hệ thống tạo một `<a>` element ẩn với `href` trỏ đến blob URL và `download` attribute chứa tên file. Tên file được tạo từ meeting title bằng cách replace các ký tự không hợp lệ (non-alphanumeric) bằng dấu gạch dưới và thêm extension `.doc`. Ví dụ, "Q3 Financial Review" sẽ trở thành "Q3_Financial_Review.doc".

Element `<a>` được append vào document body, sau đó `click()` method được gọi để trigger download. Sau khi download hoàn tất, element được remove khỏi DOM và blob URL được revoke bằng `URL.revokeObjectURL()` để giải phóng memory.

Phương pháp này tạo ra một file HTML được đóng gói với MIME type Word, cho phép Microsoft Word mở và hiển thị nội dung. Tuy nhiên, formatting có thể không hoàn toàn giống như một Word document thực sự vì Word sẽ interpret HTML theo cách riêng của nó. Để có formatting tốt hơn, hệ thống có thể sử dụng thư viện như `docx` để tạo Word documents thực sự với structure và formatting chính xác.

### Bước 4: Formatting Và Styling

HTML content được format với các styles được thiết kế để tối ưu cho cả màn hình và in ấn. Headings sử dụng font sizes khác nhau (h1: 20px, h2: 16px) với margins phù hợp để tạo hierarchy rõ ràng. Tables sử dụng `border-collapse: collapse` để có borders gọn gàng, với padding 8px cho cells và background color `#f5f5f5` cho header rows.

Meta information (date, time, minute ID) được hiển thị với font size nhỏ hơn (12px) và màu xám (#555) để phân biệt với nội dung chính. Minute ID được hiển thị với monospace font để dễ đọc và copy. Sections được cách nhau bằng margins để tạo không gian thở và dễ đọc.

Action items được hiển thị trong một table với 3 columns: Description, Assignee, và Due Date. Table có borders để tạo structure rõ ràng và dễ scan. Nếu không có action items nào, một row với colspan 3 hiển thị "None" để đảm bảo table structure vẫn hợp lệ.

Attendees được hiển thị trong một unordered list với padding-left để tạo indentation. Mỗi attendee được hiển thị với tên và role (nếu có) trong format "Name (Role)". Nếu không có attendees nào, một list item hiển thị "None" để đảm bảo section không trống.

### Bước 5: Xử Lý Edge Cases

Hệ thống xử lý các edge cases một cách graceful. Nếu meeting title rỗng, hệ thống sử dụng "Meeting Minutes" làm title mặc định. Nếu các fields như agenda, summary, hoặc decisions rỗng, chúng vẫn được hiển thị với nội dung rỗng thay vì ẩn section hoàn toàn, đảm bảo structure HTML nhất quán.

Nếu không có action items hoặc attendees, hệ thống hiển thị "None" thay vì để trống hoàn toàn. Điều này đảm bảo người dùng biết rằng section đã được kiểm tra và không có dữ liệu thay vì có thể bị thiếu.

Tên file được sanitize để loại bỏ các ký tự không hợp lệ trong tên file như `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`. Các ký tự này được replace bằng dấu gạch dưới để đảm bảo tên file hợp lệ trên tất cả các hệ điều hành.

### Tối Ưu Hóa Và Cải Thiện

Hệ thống có thể được cải thiện bằng cách sử dụng các thư viện chuyên dụng cho PDF và Word export. Đối với PDF, hệ thống có thể sử dụng jsPDF kết hợp với html2canvas để tạo PDF programmatically với chất lượng tốt hơn và không cần browser print dialog. Điều này cho phép tự động tạo và download PDF mà không cần tương tác từ người dùng.

Đối với Word, hệ thống có thể sử dụng thư viện `docx` để tạo Word documents thực sự với structure và formatting chính xác. Thư viện này cho phép tạo documents với các features như headers, footers, page breaks, tables với formatting phức tạp, và images, đảm bảo chất lượng và tương thích tốt hơn với Microsoft Word.

Ngoài ra, hệ thống có thể thêm các tính năng như watermark, header/footer với page numbers, và custom styling dựa trên template. Điều này sẽ làm cho exported documents trông chuyên nghiệp hơn và phù hợp với các yêu cầu của tổ chức.

---

## Các Đặc Điểm Kỹ Thuật Quan Trọng

Hệ thống sử dụng `asyncio.to_thread()` để chạy các hàm CPU-bound trong thread pool riêng, tránh block event loop của FastAPI và cho phép xử lý nhiều request đồng thời. Thread pool executor được cấu hình với max_workers=4 để cân bằng giữa parallelism và resource usage.

Tất cả các mô hình ML (Whisper, OpenAI client, Gemini client) được cache trong biến global và lazy load khi lần đầu được sử dụng, giúp giảm thời gian khởi động và tiết kiệm memory. File tạm thời được quản lý tự động thông qua context manager `with tempfile.TemporaryDirectory()`, đảm bảo cleanup tự động sau khi xử lý xong.

Cơ chế fallback đa tầng đảm bảo hệ thống luôn có thể xử lý được request ngay cả khi một số dịch vụ bên ngoài thất bại. Graceful degradation cho phép hệ thống trả về partial results thay vì fail hoàn toàn, cải thiện trải nghiệm người dùng.

