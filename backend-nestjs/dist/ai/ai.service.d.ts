import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
export declare class AiService {
    private readonly httpService;
    private readonly configService;
    private readonly aiServiceUrl;
    constructor(httpService: HttpService, configService: ConfigService);
    speechToText(audioFile: Express.Multer.File, language?: string): Promise<any>;
    cleanText(text: string): Promise<any>;
    summarizeText(text: string, language?: string): Promise<any>;
    diarizeText(text: string): Promise<any>;
    extractContent(text: string): Promise<any>;
    processFull(audioFile?: Express.Multer.File, transcriptFile?: Express.Multer.File, language?: string): Promise<any>;
}
