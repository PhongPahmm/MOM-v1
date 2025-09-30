import { Injectable, HttpException, HttpStatus } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';
import { ConfigService } from '@nestjs/config';

@Injectable()
export class AiService {
  private readonly aiServiceUrl: string;

  constructor(
    private readonly httpService: HttpService,
    private readonly configService: ConfigService,
  ) {
    this.aiServiceUrl = this.configService.get<string>('AI_SERVICE_URL', 'http://localhost:8001');
  }

  async speechToText(audioFile: Express.Multer.File, language: string = 'vi') {
    try {
      const formData = new FormData();
      formData.append('audio', new Blob([audioFile.buffer as unknown as ArrayBuffer]), audioFile.originalname);
      formData.append('language', language);

      const response = await firstValueFrom(
        this.httpService.post(`${this.aiServiceUrl}/speech-to-text`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }),
      );

      return response.data;
    } catch (error) {
      throw new HttpException(
        `Speech-to-text failed: ${error.message}`,
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  async cleanText(text: string) {
    try {
      const formData = new FormData();
      formData.append('text', text);

      const response = await firstValueFrom(
        this.httpService.post(`${this.aiServiceUrl}/clean`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }),
      );

      return response.data;
    } catch (error) {
      throw new HttpException(
        `Text cleaning failed: ${error.message}`,
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  async summarizeText(text: string, language: string = 'vi') {
    try {
      const formData = new FormData();
      formData.append('text', text);
      formData.append('language', language);

      const response = await firstValueFrom(
        this.httpService.post(`${this.aiServiceUrl}/summarize`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }),
      );

      return response.data;
    } catch (error) {
      throw new HttpException(
        `Summarization failed: ${error.message}`,
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  async diarizeText(text: string) {
    try {
      const formData = new FormData();
      formData.append('text', text);

      const response = await firstValueFrom(
        this.httpService.post(`${this.aiServiceUrl}/diarize`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }),
      );

      return response.data;
    } catch (error) {
      throw new HttpException(
        `Diarization failed: ${error.message}`,
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  async extractContent(text: string) {
    try {
      const formData = new FormData();
      formData.append('text', text);

      const response = await firstValueFrom(
        this.httpService.post(`${this.aiServiceUrl}/extract`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }),
      );

      return response.data;
    } catch (error) {
      throw new HttpException(
        `Content extraction failed: ${error.message}`,
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  async processFull(
    audioFile?: Express.Multer.File,
    transcriptFile?: Express.Multer.File,
    language: string = 'vi',
  ) {
    try {
      const formData = new FormData();
      
      if (audioFile) {
        formData.append('audio', new Blob([audioFile.buffer as unknown as ArrayBuffer]), audioFile.originalname);
      } else if (transcriptFile) {
        formData.append('transcript', new Blob([transcriptFile.buffer as unknown as ArrayBuffer]), transcriptFile.originalname);
      } else {
        throw new HttpException('No input file provided', HttpStatus.BAD_REQUEST);
      }
      
      formData.append('language', language);

      const response = await firstValueFrom(
        this.httpService.post(`${this.aiServiceUrl}/process-full`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }),
      );

      return response.data;
    } catch (error) {
      throw new HttpException(
        `Full processing failed: ${error.message}`,
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }
}
