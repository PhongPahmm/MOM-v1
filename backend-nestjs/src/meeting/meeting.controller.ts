import {
  Controller,
  Post,
  UploadedFile,
  UploadedFiles,
  UseInterceptors,
  Body,
  HttpException,
  HttpStatus,
} from '@nestjs/common';
import { FileInterceptor, FilesInterceptor } from '@nestjs/platform-express';
import { AiService } from '../ai/ai.service';
import { ProcessMeetingDto } from './dto/process-meeting.dto';

@Controller('meeting')
export class MeetingController {
  constructor(private readonly aiService: AiService) {}

  @Post('process')
  @UseInterceptors(FilesInterceptor('files', 2))
  async processMeeting(
    @UploadedFiles() files: Express.Multer.File[],
    @Body() body: ProcessMeetingDto,
  ) {
    try {
      if (!files || files.length === 0) {
        throw new HttpException('No files provided', HttpStatus.BAD_REQUEST);
      }

      // Determine file types
      const audioFile = files.find(file => 
        file.mimetype.startsWith('audio/') || 
        file.originalname.match(/\.(mp3|wav|m4a|flac|ogg)$/i)
      );
      
      const transcriptFile = files.find(file => 
        file.mimetype === 'text/plain' || 
        file.originalname.match(/\.(txt)$/i)
      );

      if (!audioFile && !transcriptFile) {
        throw new HttpException(
          'No valid audio or transcript file provided',
          HttpStatus.BAD_REQUEST,
        );
      }

      const result = await this.aiService.processFull(
        audioFile,
        transcriptFile,
        body.language || 'vi',
      );

      return {
        success: true,
        data: result,
      };
    } catch (error) {
      throw new HttpException(
        error.message || 'Processing failed',
        error.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Post('speech-to-text')
  @UseInterceptors(FileInterceptor('audio'))
  async speechToText(
    @UploadedFile() audioFile: Express.Multer.File,
    @Body('language') language: string = 'vi',
  ) {
    try {
      if (!audioFile) {
        throw new HttpException('No audio file provided', HttpStatus.BAD_REQUEST);
      }

      const result = await this.aiService.speechToText(audioFile, language);
      return {
        success: true,
        data: result,
      };
    } catch (error) {
      throw new HttpException(
        error.message || 'Speech-to-text failed',
        error.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Post('clean')
  async cleanText(@Body('text') text: string) {
    try {
      if (!text) {
        throw new HttpException('No text provided', HttpStatus.BAD_REQUEST);
      }

      const result = await this.aiService.cleanText(text);
      return {
        success: true,
        data: result,
      };
    } catch (error) {
      throw new HttpException(
        error.message || 'Text cleaning failed',
        error.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Post('summarize')
  async summarizeText(
    @Body('text') text: string,
    @Body('language') language: string = 'vi',
  ) {
    try {
      if (!text) {
        throw new HttpException('No text provided', HttpStatus.BAD_REQUEST);
      }

      const result = await this.aiService.summarizeText(text, language);
      return {
        success: true,
        data: result,
      };
    } catch (error) {
      throw new HttpException(
        error.message || 'Summarization failed',
        error.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Post('diarize')
  async diarizeText(@Body('text') text: string) {
    try {
      if (!text) {
        throw new HttpException('No text provided', HttpStatus.BAD_REQUEST);
      }

      const result = await this.aiService.diarizeText(text);
      return {
        success: true,
        data: result,
      };
    } catch (error) {
      throw new HttpException(
        error.message || 'Diarization failed',
        error.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Post('extract')
  async extractContent(@Body('text') text: string) {
    try {
      if (!text) {
        throw new HttpException('No text provided', HttpStatus.BAD_REQUEST);
      }

      const result = await this.aiService.extractContent(text);
      return {
        success: true,
        data: result,
      };
    } catch (error) {
      throw new HttpException(
        error.message || 'Content extraction failed',
        error.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }
}
