'use client'

import { useState } from 'react'
import { Container, Row, Col, Card, Button, Form, Nav, Tab, Badge, ListGroup, Alert } from 'react-bootstrap'
import { Upload, FileText, Mic, Download, Clock, Users, CheckCircle, AlertCircle, Edit3, Send, FileText as FileTextIcon } from 'lucide-react'
import { useDropzone } from 'react-dropzone'
import axios from 'axios'

interface ActionItem {
  description: string
  owner?: string
  due_date?: string
  priority?: string
}

interface Decision {
  text: string
  owner?: string
}

interface MomContent {
  title: string
  date?: string
  time?: string
  attendant: string[]  // Danh sách người tham dự
  project_name?: string
  customer?: string
  table_of_content: string[]  // Mục lục
  main_content: string  // Nội dung chính
  // Legacy fields for compatibility
  project?: string
  attendees: Array<{ name: string; role?: string }>
  agenda: string[]
  summary: string
  key_points: string[]
  decisions: Decision[]
  action_items: ActionItem[]
}

interface ProcessResponse {
  transcript?: string
  structured_summary?: {
    title?: string
    date?: string
    time?: string
    attendants?: string[]
    project_name?: string
    customer?: string
    table_of_content?: string[]
    main_content?: string
  }
  action_items?: ActionItem[]
  decisions?: Decision[]
  diarization?: any[]
}

export default function Home() {
  const [isProcessing, setIsProcessing] = useState(false)
  const [result, setResult] = useState<ProcessResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [language, setLanguage] = useState('vi')
  const [activeTab, setActiveTab] = useState<'transcript' | 'mom'>('transcript')
  
  // State for editable MoM data
  const [editableMom, setEditableMom] = useState<MomContent | null>(null)

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      'audio/*': ['.mp3', '.wav', '.m4a', '.ogg'],
      'text/*': ['.txt', '.md']
    },
    multiple: false,
    onDrop: async (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        await processFile(acceptedFiles[0])
      }
    }
  })

  const processFile = async (file: File) => {
    setIsProcessing(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('language', language)
      
      if (file.type.startsWith('audio/')) {
        formData.append('files', file)
      } else {
        formData.append('files', file)
      }

      const response = await axios.post('http://localhost:3000/meeting/process', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      setResult(response.data.data)
      // Auto-fill editable MoM data
      const responseData = response.data.data
      if (responseData.structured_summary) {
        // Map structured_summary to MomContent format
        const momData: MomContent = {
          title: responseData.structured_summary.title || 'Meeting Minutes',
          date: responseData.structured_summary.date || 'N/A',
          time: responseData.structured_summary.time || 'N/A',
          attendant: responseData.structured_summary.attendants || [],
          project_name: responseData.structured_summary.project_name || '',
          customer: responseData.structured_summary.customer || '',
          table_of_content: responseData.structured_summary.table_of_content || [],
          main_content: responseData.structured_summary.main_content || '',
          // Legacy fields
          project: responseData.structured_summary.project_name || '',
          attendees: (responseData.structured_summary.attendants || []).map((name: string) => ({ name })),
          agenda: responseData.structured_summary.table_of_content || [],
          summary: responseData.structured_summary.main_content || '',
          key_points: [],
          decisions: responseData.decisions || [],
          action_items: responseData.action_items || []
        }
        
        // Auto-generate action items from transcript if none exist
        if (!responseData.action_items || responseData.action_items.length === 0) {
          const autoActionItems = generateActionItemsFromTranscript(responseData.transcript || '')
          momData.action_items = autoActionItems
          console.log('Auto-generated action items from transcript:', autoActionItems)
        }
        
        setEditableMom(momData)
        console.log('Auto-filled MoM data from structured_summary:', momData)
      } else {
        console.log('No structured_summary found in response:', responseData)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred while processing the file')
    } finally {
      setIsProcessing(false)
    }
  }

  const exportToPDF = () => {
    if (!editableMom) return
    
    // Generate filename with current date
    const currentDate = new Date().toISOString().split('T')[0]
    const filename = `meeting-minutes-${currentDate}.html`
    
    // Simple HTML export - in a real app, you'd use a proper PDF library
    const htmlContent = generateHTMLContent(editableMom)
    const blob = new Blob([htmlContent], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    
    // Show success message
    alert(`File đã được lưu vào thư mục Downloads: ${filename}`)
  }

  // Update editable MoM data
  const updateEditableMom = (field: keyof MomContent, value: any) => {
    if (!editableMom) return
    setEditableMom({
      ...editableMom,
      [field]: value
    })
  }

  // Highlight keywords in text
  const highlightKeywords = (text: string) => {
    if (!text) return text
    
    // Patterns for highlighting
    const patterns = [
      // Time patterns (10:45 AM, 2:30 PM, etc.)
      { regex: /\b\d{1,2}:\d{2}\s*(AM|PM|am|pm)\b/g, className: 'highlight-time' },
      // Date patterns (December 1st, 2025, 15/12/2025, etc.)
      { regex: /\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(st|nd|rd|th)?,?\s*\d{4}\b/g, className: 'highlight-date' },
      { regex: /\b\d{1,2}\/\d{1,2}\/\d{4}\b/g, className: 'highlight-date' },
      // Name patterns (capitalized words that could be names)
      { regex: /\b[A-Z][a-z]+\s+[A-Z][a-z]+\b/g, className: 'highlight-name' },
      // Task keywords
      { regex: /\b(finalize|prepare|create|complete|review|update|implement|coordinate|schedule|meeting|project|report|plan|assessment)\b/gi, className: 'highlight-task' }
    ]

    let highlightedText = text
    patterns.forEach(pattern => {
      highlightedText = highlightedText.replace(pattern.regex, `<mark class="${pattern.className}">$&</mark>`)
    })

    return highlightedText
  }

  // Generate action items from transcript
  const generateActionItemsFromTranscript = (transcript: string): ActionItem[] => {
    if (!transcript) return []
    
    const actionItems: ActionItem[] = []
    const lines = transcript.split('\n')
    
    // Common action item patterns
    const actionPatterns = [
      /(?:need to|will|should|must|have to|going to)\s+([^.!?]+)/gi,
      /(?:action item|todo|task|follow up|next step)[:\s]*([^.!?]+)/gi,
      /(?:assign|delegate|give)\s+([^.!?]+)\s+(?:to|for)/gi,
      /(?:deadline|due|by)\s+([^.!?]+)/gi
    ]
    
    lines.forEach((line, index) => {
      actionPatterns.forEach(pattern => {
        const matches = line.match(pattern)
        if (matches) {
          matches.forEach(match => {
            const description = match.replace(/(?:need to|will|should|must|have to|going to|action item|todo|task|follow up|next step|assign|delegate|give|deadline|due|by)[:\s]*/gi, '').trim()
            if (description && description.length > 10) {
              actionItems.push({
                description: description,
                owner: '',
                due_date: '',
                priority: 'medium'
              })
            }
          })
        }
      })
    })
    
    // Remove duplicates and limit to 5 items
    const uniqueItems = actionItems.filter((item, index, self) => 
      index === self.findIndex(t => t.description === item.description)
    ).slice(0, 5)
    
    return uniqueItems
  }

  const generateHTMLContent = (mom: MomContent) => {
    return `
      <!DOCTYPE html>
      <html>
      <head>
        <title>${mom?.title || 'Meeting Minutes'}</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
          h1 { color: #2563eb; border-bottom: 2px solid #2563eb; padding-bottom: 10px; }
          h2 { color: #374151; margin-top: 30px; }
          .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }
          .info-item { background: #f9fafb; padding: 15px; border-radius: 8px; }
          .attendants { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }
          .attendant-tag { background: #dbeafe; color: #1e40af; padding: 4px 12px; border-radius: 20px; font-size: 14px; }
          .main-content { background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0; }
          .action-item, .decision { background: #f9fafb; padding: 15px; margin: 10px 0; border-left: 4px solid #2563eb; }
          .table-of-content ul { padding-left: 20px; }
        </style>
      </head>
      <body>
        <h1>${mom?.title || 'Meeting Minutes'}</h1>
        
        <div class="info-grid">
          <div class="info-item">
            <strong>Date:</strong> ${mom?.date || 'N/A'}
          </div>
          <div class="info-item">
            <strong>Time:</strong> ${mom?.time || 'N/A'}
          </div>
          ${mom?.project_name ? `<div class="info-item">
            <strong>Project Name:</strong> ${mom.project_name}
          </div>` : ''}
          ${mom?.customer ? `<div class="info-item">
            <strong>Customer:</strong> ${mom.customer}
          </div>` : ''}
        </div>
        
        ${mom?.attendant && mom.attendant.length > 0 ? `
        <h2>Attendants</h2>
        <div class="attendants">
          ${mom.attendant.map(person => `<span class="attendant-tag">${person}</span>`).join('')}
        </div>
        ` : ''}
        
        ${mom?.table_of_content && mom.table_of_content.length > 0 ? `
        <h2>Table of Content</h2>
        <div class="table-of-content">
          <ul>
            ${mom.table_of_content.map(item => `<li>${item}</li>`).join('')}
          </ul>
        </div>
        ` : ''}
        
        ${mom?.main_content ? `
        <h2>Main Content</h2>
        <div class="main-content">${mom.main_content}</div>
        ` : ''}
        
        ${mom?.key_points && mom.key_points.length > 0 ? `
        <h2>Key Points</h2>
        <ul>
          ${mom.key_points.map(point => `<li>${point}</li>`).join('')}
        </ul>
        ` : ''}
        
        ${mom?.decisions && mom.decisions.length > 0 ? `
        <h2>Decisions</h2>
        ${mom.decisions.map(decision => `
          <div class="decision">
            <strong>Decision:</strong> ${decision.text}
            ${decision.owner ? `<br><strong>Owner:</strong> ${decision.owner}` : ''}
          </div>
        `).join('')}
        ` : ''}
        
        ${mom?.action_items && mom.action_items.length > 0 ? `
        <h2>Action Items</h2>
        ${mom.action_items.map(action => `
          <div class="action-item">
            <strong>Action:</strong> ${action.description}
            ${action.owner ? `<br><strong>Owner:</strong> ${action.owner}` : ''}
            ${action.due_date ? `<br><strong>Due Date:</strong> ${action.due_date}` : ''}
            ${action.priority ? `<br><strong>Priority:</strong> ${action.priority}` : ''}
          </div>
        `).join('')}
        ` : ''}
      </body>
    </html>
    `
  }

  return (
    <div className="meeting-editor">
      <Container fluid className="py-4">
        <Row className="justify-content-center">
          <Col lg={10} xl={8}>
            <div className="text-center mb-4">
              <h1 className="display-4 fw-bold text-primary mb-2">Smart Meeting Minutes</h1>
              <p className="lead text-muted">Upload audio or transcript to generate intelligent meeting summaries</p>
        </div>

          {/* Language Selection */}
            <Row className="mb-4">
              <Col md={4}>
                <Form.Group>
                  <Form.Label>Language</Form.Label>
                  <Form.Select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              <option value="vi">Vietnamese</option>
              <option value="en">English</option>
                  </Form.Select>
                </Form.Group>
              </Col>
            </Row>

          {/* File Upload Area */}
            <Card className="mb-4">
              <Card.Body>
          <div
            {...getRootProps()}
                  className={`border-2 border-dashed rounded p-5 text-center cursor-pointer ${
                    isDragActive ? 'border-primary bg-primary bg-opacity-10' : 'border-secondary'
            }`}
          >
            <input {...getInputProps()} />
                  <div className="d-flex flex-column align-items-center">
              {isDragActive ? (
                      <Upload size={48} className="text-primary mb-3" />
                    ) : (
                      <div className="d-flex gap-3 mb-3">
                        <Mic size={48} className="text-muted" />
                        <FileText size={48} className="text-muted" />
                </div>
              )}
                    <h4 className="mb-2">
                {isDragActive ? 'Drop your file here' : 'Upload audio or transcript'}
                    </h4>
                    <p className="text-muted mb-3">
                Drag and drop a file here, or click to select
              </p>
                    <small className="text-muted">
                Supports: MP3, WAV, M4A, OGG audio files or TXT, MD text files
                    </small>
            </div>
          </div>
              </Card.Body>
            </Card>

          {/* Processing State */}
          {isProcessing && (
              <Alert variant="info" className="text-center">
                <Clock size={20} className="me-2" />
                Processing your file...
              </Alert>
          )}

          {/* Error Display */}
          {error && (
              <Alert variant="danger">
                <AlertCircle size={20} className="me-2" />
                {error}
              </Alert>
          )}

          {/* Results Display */}
          {result && (
              <div className="mt-4">
                <Tab.Container activeKey={activeTab} onSelect={(k) => setActiveTab(k as 'transcript' | 'mom')}>
                  <Nav variant="tabs" className="mb-3">
                    <Nav.Item>
                      <Nav.Link eventKey="transcript">Transcript</Nav.Link>
                    </Nav.Item>
                    <Nav.Item>
                      <Nav.Link eventKey="mom">
                        <Edit3 size={16} className="me-1" />
                        MoM Editor
                        {editableMom && <Badge bg="success" className="ms-2">Auto-filled</Badge>}
                      </Nav.Link>
                    </Nav.Item>
                  </Nav>

                  <Tab.Content>
                    <Tab.Pane eventKey="transcript">
                      <Card>
                        <Card.Header>
                          <h5 className="mb-0">Original Transcript</h5>
                          <small className="text-muted">Raw content extracted from the uploaded file with keyword highlights.</small>
                        </Card.Header>
                        <Card.Body>
                          {result.transcript && (
                            <div className="bg-light p-3 rounded" style={{ maxHeight: '400px', overflowY: 'auto' }}>
                              <div 
                                dangerouslySetInnerHTML={{ 
                                  __html: highlightKeywords(result.transcript) 
                                }}
                                style={{ 
                                  whiteSpace: 'pre-wrap',
                                  lineHeight: '1.6',
                                  fontSize: '0.875rem',
                                  fontFamily: 'monospace'
                                }}
                              />
                            </div>
                          )}
                        </Card.Body>
                      </Card>
                    </Tab.Pane>

                    <Tab.Pane eventKey="mom">
                      {/* Debug Info */}
                      {!editableMom && result && (
                        <Alert variant="info">
                          <AlertCircle size={20} className="me-2" />
                          Processing MoM data from structured_summary...
                        </Alert>
                      )}
                      
                      {/* Action Bar */}
                      <Card className="mb-3">
                        <Card.Body>
                          <Row className="align-items-center">
                            <Col md={6}>
                              <Form.Group className="mb-0">
                                <Form.Label className="me-2">Template:</Form.Label>
                                <Form.Select style={{ width: 'auto', display: 'inline-block' }}>
                                  <option>Default Meeting Template</option>
                                </Form.Select>
                              </Form.Group>
                            </Col>
                            <Col md={6} className="text-md-end">
                              <div className="d-flex gap-2 justify-content-md-end">
                                <Button variant="outline-secondary" size="sm" onClick={exportToPDF}>
                                  <FileTextIcon size={16} className="me-1" />
                                  Export PDF
                                </Button>
                                <Button variant="outline-secondary" size="sm">
                                  <FileTextIcon size={16} className="me-1" />
                                  Export Word
                                </Button>
                                <Button variant="primary" size="sm">
                                  <Send size={16} className="me-1" />
                                  Send Email
                                </Button>
                </div>
                            </Col>
                          </Row>
                        </Card.Body>
                      </Card>

                      {/* Meeting Details Form */}
                      <Card className="mb-3">
                        <Card.Header>
                          <h5 className="mb-0">
                            <CheckCircle size={20} className="me-2 text-success" />
                            Meeting Information
                          </h5>
                        </Card.Header>
                        <Card.Body>
                          <Row>
                            <Col md={6}>
                              <Form.Group className="mb-3">
                                <Form.Label>Meeting Title</Form.Label>
                                <Form.Control
                                  type="text"
                                  value={editableMom?.title || ''}
                                  onChange={(e) => updateEditableMom('title', e.target.value)}
                                  placeholder="Enter meeting title"
                                />
                              </Form.Group>
                            </Col>
                            <Col md={6}>
                              <Form.Group className="mb-3">
                                <Form.Label>Date & Time</Form.Label>
                                <Form.Control
                                  type="text"
                                  value={`${editableMom?.date || 'N/A'}, ${editableMom?.time || 'N/A'}`}
                                  onChange={(e) => {
                                    const [date, time] = e.target.value.split(', ')
                                    updateEditableMom('date', date)
                                    updateEditableMom('time', time)
                                  }}
                                  placeholder="Select date and time"
                                />
                              </Form.Group>
                            </Col>
                          </Row>
                          
                          <Form.Group className="mb-3">
                            <Form.Label>Attendees</Form.Label>
                            <div className="d-flex flex-wrap gap-2 mb-2">
                              {editableMom?.attendant && editableMom.attendant.map((person, index) => (
                                <Badge key={index} bg="primary" className="d-flex align-items-center">
                          {person}
                                  <button 
                                    className="btn-close btn-close-white ms-2" 
                                    style={{ fontSize: '0.5rem' }}
                                    onClick={() => {
                                      const newAttendants = editableMom.attendant.filter((_, i) => i !== index)
                                      updateEditableMom('attendant', newAttendants)
                                    }}
                                  ></button>
                                </Badge>
                      ))}
                    </div>
                            <Form.Control
                              type="text"
                              placeholder="Add attendee name"
                              onKeyPress={(e) => {
                                if (e.key === 'Enter') {
                                  const newAttendant = e.currentTarget.value.trim()
                                  if (newAttendant && editableMom) {
                                    updateEditableMom('attendant', [...editableMom.attendant, newAttendant])
                                    e.currentTarget.value = ''
                                  }
                                }
                              }}
                            />
                          </Form.Group>
                        </Card.Body>
                      </Card>

                      {/* Agenda */}
                      {editableMom?.table_of_content && editableMom.table_of_content.length > 0 && (
                        <Card className="mb-3">
                          <Card.Header>
                            <h5 className="mb-0">
                              <FileTextIcon size={20} className="me-2 text-primary" />
                              Agenda
                            </h5>
                          </Card.Header>
                          <Card.Body>
                            <ListGroup variant="flush">
                              {editableMom.table_of_content.map((item, index) => (
                                <ListGroup.Item key={index} className="d-flex">
                                  <span className="me-2 fw-bold text-primary">{index + 1}.</span>
                                  <Form.Control
                                    type="text"
                                    value={item}
                                    onChange={(e) => {
                                      const newTableOfContent = [...editableMom.table_of_content]
                                      newTableOfContent[index] = e.target.value
                                      updateEditableMom('table_of_content', newTableOfContent)
                                    }}
                                    className="border-0 p-0 bg-transparent"
                                  />
                                </ListGroup.Item>
                              ))}
                            </ListGroup>
                          </Card.Body>
                        </Card>
                      )}

                      {/* Meeting Summary */}
                      {editableMom?.main_content && (
                        <Card className="mb-3">
                          <Card.Header>
                            <h5 className="mb-0">
                              <FileTextIcon size={20} className="me-2 text-primary" />
                              Meeting Summary
                            </h5>
                          </Card.Header>
                          <Card.Body>
                            <div className="mb-3">
                              <Form.Control
                                as="textarea"
                                rows={6}
                                value={editableMom.main_content}
                                onChange={(e) => updateEditableMom('main_content', e.target.value)}
                                style={{ whiteSpace: 'pre-wrap' }}
                                placeholder="Enter meeting summary..."
                              />
                            </div>
                            <div className="bg-light p-3 rounded">
                              <h6 className="mb-2">Preview with Highlights:</h6>
                              <div 
                                dangerouslySetInnerHTML={{ 
                                  __html: highlightKeywords(editableMom.main_content) 
                                }}
                                style={{ 
                                  whiteSpace: 'pre-wrap',
                                  lineHeight: '1.6',
                                  fontSize: '0.9rem'
                                }}
                              />
                            </div>
                          </Card.Body>
                        </Card>
                      )}

                      {/* Key Decisions */}
                      {editableMom?.decisions && editableMom.decisions.length > 0 && (
                        <Card className="mb-3">
                          <Card.Header>
                            <h5 className="mb-0">
                              <Users size={20} className="me-2 text-primary" />
                              Key Decisions
                            </h5>
                          </Card.Header>
                          <Card.Body>
                            {editableMom.decisions.map((decision, index) => (
                              <Card key={index} className="mb-3 border-start border-primary border-4">
                                <Card.Body>
                                  <Row>
                                    <Col md={8}>
                                      <Form.Group>
                                        <Form.Label className="small">Decision</Form.Label>
                                        <Form.Control
                                          type="text"
                                          value={decision.text}
                                          onChange={(e) => {
                                            const newDecisions = [...editableMom.decisions]
                                            newDecisions[index] = { ...decision, text: e.target.value }
                                            updateEditableMom('decisions', newDecisions)
                                          }}
                                          placeholder="Enter decision"
                                        />
                                      </Form.Group>
                                    </Col>
                                    <Col md={4}>
                                      <Form.Group>
                                        <Form.Label className="small">Owner</Form.Label>
                                        <Form.Control
                                          type="text"
                                          value={decision.owner || ''}
                                          onChange={(e) => {
                                            const newDecisions = [...editableMom.decisions]
                                            newDecisions[index] = { ...decision, owner: e.target.value }
                                            updateEditableMom('decisions', newDecisions)
                                          }}
                                          placeholder="Enter owner"
                                        />
                                      </Form.Group>
                                    </Col>
                                  </Row>
                                </Card.Body>
                              </Card>
                            ))}
                          </Card.Body>
                        </Card>
              )}

                      {/* Action Items */}
                      <Card className="mb-3">
                        <Card.Header>
                          <h5 className="mb-0">
                            <AlertCircle size={20} className="me-2 text-warning" />
                            Action Items
                          </h5>
                        </Card.Header>
                        <Card.Body>
                          {editableMom?.action_items && editableMom.action_items.length > 0 ? (
                            editableMom.action_items.map((action, index) => (
                              <div key={index} className="action-item-card">
                                <div className="action-item-content">
                                  <div className="action-item-description">
                                    <Form.Label className="small fw-bold">Task Description</Form.Label>
                                    <Form.Control
                                      as="textarea"
                                      rows={2}
                                      value={action.description}
                                      onChange={(e) => {
                                        const newActionItems = [...editableMom.action_items]
                                        newActionItems[index] = { ...action, description: e.target.value }
                                        updateEditableMom('action_items', newActionItems)
                                      }}
                                      placeholder="Enter task description..."
                                      className="border-0 bg-transparent p-0"
                                    />
                                  </div>
                                  <div className="action-item-assignee">
                                    <Form.Label className="small fw-bold">Assignee</Form.Label>
                                    <Form.Control
                                      type="text"
                                      value={action.owner || ''}
                                      onChange={(e) => {
                                        const newActionItems = [...editableMom.action_items]
                                        newActionItems[index] = { ...action, owner: e.target.value }
                                        updateEditableMom('action_items', newActionItems)
                                      }}
                                      placeholder="Assignee"
                                      className="border-0 bg-transparent p-0"
                                    />
                                  </div>
                                  <div className="action-item-due-date">
                                    <Form.Label className="small fw-bold">Due Date</Form.Label>
                                    <Form.Control
                                      type="text"
                                      value={action.due_date || ''}
                                      onChange={(e) => {
                                        const newActionItems = [...editableMom.action_items]
                                        newActionItems[index] = { ...action, due_date: e.target.value }
                                        updateEditableMom('action_items', newActionItems)
                                      }}
                                      placeholder="dd/mm/yyyy"
                                      className="border-0 bg-transparent p-0"
                                    />
                                  </div>
                                  <div className="action-item-delete">
                                    <Button 
                                      variant="outline-danger" 
                                      size="sm"
                                      onClick={() => {
                                        const newActionItems = editableMom.action_items.filter((_, i) => i !== index)
                                        updateEditableMom('action_items', newActionItems)
                                      }}
                                      className="p-1"
                                    >
                                      🗑️
                                    </Button>
                                  </div>
                                </div>
                              </div>
                            ))
                          ) : (
                            <div className="text-center text-muted py-4">
                              <AlertCircle size={48} className="mb-2" />
                              <p>No action items found. Add some tasks to track progress.</p>
                            </div>
                          )}
                          
                          {/* Add new action item button */}
                          <div className="text-center mt-3">
                            <Button 
                              variant="outline-primary" 
                              size="sm"
                              onClick={() => {
                                const newActionItem = {
                                  description: '',
                                  owner: '',
                                  due_date: '',
                                  priority: 'medium'
                                }
                                const currentItems = editableMom?.action_items || []
                                updateEditableMom('action_items', [...currentItems, newActionItem])
                              }}
                            >
                              + Add Action Item
                            </Button>
                          </div>
                        </Card.Body>
                      </Card>
                    </Tab.Pane>
                  </Tab.Content>
                </Tab.Container>
                </div>
              )}
          </Col>
        </Row>
      </Container>
    </div>
  )
}