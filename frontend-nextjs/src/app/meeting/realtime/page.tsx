"use client";

import { useEffect, useRef, useState } from "react";
import { Container, Row, Col, Card, Button, Form, Alert } from "react-bootstrap";
import Link from "next/link";

// Extend window interface for speech recognition
declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
  
  interface MediaDevices {
    getDisplayMedia(constraints?: MediaStreamConstraints): Promise<MediaStream>;
  }
}

export default function RealtimeMeetingPage() {
  const [isSupported, setIsSupported] = useState<boolean>(false);
  const [listening, setListening] = useState<boolean>(false);
  const [language, setLanguage] = useState<string>("vi-VN");
  const [interimText, setInterimText] = useState<string>("");
  const [finalText, setFinalText] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [screenError, setScreenError] = useState<string | null>(null);
  const [isSharing, setIsSharing] = useState<boolean>(false);
  const [transcriptHistory, setTranscriptHistory] = useState<Array<{timestamp: string, text: string}>>([]);
  const [sessionStartTime, setSessionStartTime] = useState<Date | null>(null);

  // Auto-save to localStorage
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('realtime-transcript');
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          setFinalText(parsed.finalText || '');
          setTranscriptHistory(parsed.transcriptHistory || []);
          if (parsed.sessionStartTime) {
            setSessionStartTime(new Date(parsed.sessionStartTime));
          }
        } catch (e) {
          console.error('Error loading saved transcript:', e);
        }
      }
    }
  }, []);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const dataToSave = {
        finalText,
        transcriptHistory,
        sessionStartTime: sessionStartTime?.toISOString()
      };
      localStorage.setItem('realtime-transcript', JSON.stringify(dataToSave));
    }
  }, [finalText, transcriptHistory, sessionStartTime]);

  const recognitionRef = useRef<any>(null);
  const screenVideoRef = useRef<HTMLVideoElement | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      setIsSupported(true);
      const recognition = new SpeechRecognition();
      recognition.interimResults = true;
      recognition.continuous = true;
      recognition.lang = 'vi-VN';

      recognition.onresult = (event: any) => {
        let interim = "";
        let finalStr = finalText;
        let newFinalTexts: string[] = [];
        
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            const trimmedTranscript = transcript.trim();
            if (trimmedTranscript) {
              finalStr += (finalStr ? "\n" : "") + trimmedTranscript;
              newFinalTexts.push(trimmedTranscript);
            }
          } else {
            interim += transcript;
          }
        }
        
        // Add new final texts to history with timestamps
        if (newFinalTexts.length > 0) {
          const currentTime = new Date();
          const timestamp = currentTime.toLocaleTimeString('vi-VN', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
          });
          
          setTranscriptHistory(prev => [
            ...prev,
            ...newFinalTexts.map(text => ({ timestamp, text }))
          ]);
        }
        
        setInterimText(interim);
        setFinalText(finalStr);
      };

      recognition.onerror = (e: any) => {
        setError(e?.error || "Speech recognition error");
        setListening(false);
      };

      recognition.onend = () => {
        setListening(false);
      };

      recognitionRef.current = recognition;
    } else {
      setIsSupported(false);
    }
  }, []);


  const startListening = async () => {
    if (!recognitionRef.current) return;
    try {
      setError(null);
      recognitionRef.current.start();
      setListening(true);
      setSessionStartTime(new Date());
    } catch (e: unknown) {
      setError((e as Error)?.message || "Cannot start recognition");
    }
  };

  const stopListening = () => {
    const recognition = recognitionRef.current;
    if (!recognition) return;
    try {
      // Stop recognition gracefully; fallback to abort if needed
      if (typeof recognition.stop === 'function') {
        recognition.stop();
      }
      if (listening && typeof recognition.abort === 'function') {
        // Some browsers require abort to immediately end
        recognition.abort();
      }
    } catch (e) {
      // no-op
    } finally {
      setListening(false);
      setInterimText("");
    }
  };

  const clearText = () => {
    setInterimText("");
    setFinalText("");
    setTranscriptHistory([]);
    setSessionStartTime(null);
    if (typeof window !== 'undefined') {
      localStorage.removeItem('realtime-transcript');
    }
  };

  const exportTranscript = () => {
    if (!finalText.trim()) {
      setError("Không có transcript để export");
      return;
    }

    const sessionInfo = sessionStartTime 
      ? `Session started: ${sessionStartTime.toLocaleString('vi-VN')}\n` +
        `Session ended: ${new Date().toLocaleString('vi-VN')}\n` +
        `Total duration: ${Math.round((new Date().getTime() - sessionStartTime.getTime()) / 1000)} seconds\n\n`
      : '';

    const historySectionHeader = "=== TRANSCRIPT WITH TIMESTAMPS ===\n\n";
    const historyBody = transcriptHistory.length > 0
      ? transcriptHistory.map(item => `[${item.timestamp}] ${item.text}`).join('\n')
      : "(no entries)";
    const timestampedContent = sessionInfo + historySectionHeader + historyBody;

    const blob = new Blob([timestampedContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `transcript_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const startScreenShare = async () => {
    try {
      setScreenError(null);
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: 30 },
        audio: false,
      });
      screenStreamRef.current = stream;
      if (screenVideoRef.current) {
        screenVideoRef.current.srcObject = stream;
        await screenVideoRef.current.play();
      }
      setIsSharing(true);
      // Handle when user stops from browser UI
      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        stopScreenShare();
      });
    } catch (e: unknown) {
      setScreenError((e as Error)?.message || "Không thể bật chia sẻ màn hình");
      setIsSharing(false);
    }
  };

  const stopScreenShare = () => {
    try {
      const stream = screenStreamRef.current;
      stream?.getTracks().forEach((t) => t.stop());
      screenStreamRef.current = null;
      if (screenVideoRef.current) {
        screenVideoRef.current.srcObject = null;
      }
    } finally {
      setIsSharing(false);
    }
  };

  return (
    <Container className="py-4">
      <Row className="justify-content-center">
        <Col md={10} lg={8} xl={7}>
          <div className="d-flex justify-content-between align-items-center mb-3">
            <div>
              <h1 className="fw-bold mb-0">Realtime Meeting</h1>
              <div className="text-muted">Nhận transcript theo thời gian thực bằng trình duyệt</div>
            </div>
            <Link href="/" className="btn btn-outline-secondary">Home</Link>
          </div>

          {!isSupported && (
            <Alert variant="warning">
              Trình duyệt của bạn chưa hỗ trợ Web Speech API. Hãy dùng Chrome-based browser.
            </Alert>
          )}

          {error && (
            <Alert variant="danger" className="mb-3">{error}</Alert>
          )}

          <Card className="mb-3">
            <Card.Body>
              <Row className="g-3 align-items-end">
                <Col md={12} className="text-end">
                  {!listening ? (
                    <Button variant="primary" onClick={startListening} disabled={!isSupported}>
                      Bắt đầu
                    </Button>
                  ) : (
                    <Button variant="danger" onClick={stopListening}>
                      Dừng
                    </Button>
                  )}
                  <Button variant="outline-secondary" className="ms-2" onClick={clearText}>
                    Xóa
                  </Button>
                  <Button 
                    variant="outline-success" 
                    className="ms-2" 
                    onClick={exportTranscript}
                    disabled={!finalText.trim()}
                  >
                    Export
                  </Button>
                  {!isSharing ? (
                    <Button variant="outline-dark" className="ms-2" onClick={startScreenShare}>
                      Share màn hình
                    </Button>
                  ) : (
                    <Button variant="dark" className="ms-2" onClick={stopScreenShare}>
                      Dừng share
                    </Button>
                  )}
                </Col>
              </Row>
            </Card.Body>
          </Card>

          {screenError && (
            <Alert variant="warning">{screenError}</Alert>
          )}

          <Row>
            <Col md={12}>
              <Card className="mb-3">
                <Card.Header>
                  <strong>Transcript (Realtime)</strong>
                  {sessionStartTime && (
                    <small className="text-muted ms-2">
                      - Session started: {sessionStartTime.toLocaleTimeString('vi-VN')}
                    </small>
                  )}
                </Card.Header>
                <Card.Body>
                  <div className="mb-2 text-muted" style={{ minHeight: 24 }}>
                    {interimText && <span className="text-primary">Đang nhận diện: {interimText}</span>}
                  </div>
                  <pre style={{ whiteSpace: "pre-wrap", minHeight: 200, maxHeight: 400, overflowY: 'auto' }}>
{finalText}
                  </pre>
                </Card.Body>
              </Card>
            </Col>
            
            {transcriptHistory.length > 0 && (
              <Col md={12}>
                <Card className="mb-3">
                  <Card.Header>
                    <strong>Transcript History (with Timestamps)</strong>
                    <small className="text-muted ms-2">- {transcriptHistory.length} entries</small>
                  </Card.Header>
                  <Card.Body>
                    <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                      {transcriptHistory.map((entry, index) => (
                        <div key={index} className="mb-2 p-2 border-start border-3 border-primary">
                          <small className="text-muted fw-bold">[{entry.timestamp}]</small>
                          <div className="mt-1">{entry.text}</div>
                        </div>
                      ))}
                    </div>
                  </Card.Body>
                </Card>
              </Col>
            )}
            <Col md={12}>
              <Card className="mb-3">
                <Card.Header>
                  <strong>Screen share</strong>
                </Card.Header>
                <Card.Body>
                  {isSharing ? (
                    <video
                      ref={screenVideoRef}
                      style={{ width: "100%", borderRadius: 8 }}
                      muted
                      playsInline
                      autoPlay
                    />
                  ) : (
                    <div className="text-muted">Chưa chia sẻ màn hình</div>
                  )}
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </Col>
      </Row>
    </Container>
  );
}


