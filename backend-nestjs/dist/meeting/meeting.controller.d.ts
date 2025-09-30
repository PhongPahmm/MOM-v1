import { AiService } from '../ai/ai.service';
import { ProcessMeetingDto } from './dto/process-meeting.dto';
export declare class MeetingController {
    private readonly aiService;
    constructor(aiService: AiService);
    processMeeting(files: Express.Multer.File[], body: ProcessMeetingDto): Promise<{
        success: boolean;
        data: any;
    }>;
    speechToText(audioFile: Express.Multer.File, language?: string): Promise<{
        success: boolean;
        data: any;
    }>;
    cleanText(text: string): Promise<{
        success: boolean;
        data: any;
    }>;
    summarizeText(text: string, language?: string): Promise<{
        success: boolean;
        data: any;
    }>;
    diarizeText(text: string): Promise<{
        success: boolean;
        data: any;
    }>;
    extractContent(text: string): Promise<{
        success: boolean;
        data: any;
    }>;
}
