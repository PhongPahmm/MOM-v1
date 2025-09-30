"use strict";
var __decorate = (this && this.__decorate) || function (decorators, target, key, desc) {
    var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
    if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
    else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
    return c > 3 && r && Object.defineProperty(target, key, r), r;
};
var __metadata = (this && this.__metadata) || function (k, v) {
    if (typeof Reflect === "object" && typeof Reflect.metadata === "function") return Reflect.metadata(k, v);
};
var __param = (this && this.__param) || function (paramIndex, decorator) {
    return function (target, key) { decorator(target, key, paramIndex); }
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.MeetingController = void 0;
const common_1 = require("@nestjs/common");
const platform_express_1 = require("@nestjs/platform-express");
const ai_service_1 = require("../ai/ai.service");
const process_meeting_dto_1 = require("./dto/process-meeting.dto");
let MeetingController = class MeetingController {
    aiService;
    constructor(aiService) {
        this.aiService = aiService;
    }
    async processMeeting(files, body) {
        try {
            if (!files || files.length === 0) {
                throw new common_1.HttpException('No files provided', common_1.HttpStatus.BAD_REQUEST);
            }
            const audioFile = files.find(file => file.mimetype.startsWith('audio/') ||
                file.originalname.match(/\.(mp3|wav|m4a|flac|ogg)$/i));
            const transcriptFile = files.find(file => file.mimetype === 'text/plain' ||
                file.originalname.match(/\.(txt)$/i));
            if (!audioFile && !transcriptFile) {
                throw new common_1.HttpException('No valid audio or transcript file provided', common_1.HttpStatus.BAD_REQUEST);
            }
            const result = await this.aiService.processFull(audioFile, transcriptFile, body.language || 'vi');
            return {
                success: true,
                data: result,
            };
        }
        catch (error) {
            throw new common_1.HttpException(error.message || 'Processing failed', error.status || common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    async speechToText(audioFile, language = 'vi') {
        try {
            if (!audioFile) {
                throw new common_1.HttpException('No audio file provided', common_1.HttpStatus.BAD_REQUEST);
            }
            const result = await this.aiService.speechToText(audioFile, language);
            return {
                success: true,
                data: result,
            };
        }
        catch (error) {
            throw new common_1.HttpException(error.message || 'Speech-to-text failed', error.status || common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    async cleanText(text) {
        try {
            if (!text) {
                throw new common_1.HttpException('No text provided', common_1.HttpStatus.BAD_REQUEST);
            }
            const result = await this.aiService.cleanText(text);
            return {
                success: true,
                data: result,
            };
        }
        catch (error) {
            throw new common_1.HttpException(error.message || 'Text cleaning failed', error.status || common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    async summarizeText(text, language = 'vi') {
        try {
            if (!text) {
                throw new common_1.HttpException('No text provided', common_1.HttpStatus.BAD_REQUEST);
            }
            const result = await this.aiService.summarizeText(text, language);
            return {
                success: true,
                data: result,
            };
        }
        catch (error) {
            throw new common_1.HttpException(error.message || 'Summarization failed', error.status || common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    async diarizeText(text) {
        try {
            if (!text) {
                throw new common_1.HttpException('No text provided', common_1.HttpStatus.BAD_REQUEST);
            }
            const result = await this.aiService.diarizeText(text);
            return {
                success: true,
                data: result,
            };
        }
        catch (error) {
            throw new common_1.HttpException(error.message || 'Diarization failed', error.status || common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    async extractContent(text) {
        try {
            if (!text) {
                throw new common_1.HttpException('No text provided', common_1.HttpStatus.BAD_REQUEST);
            }
            const result = await this.aiService.extractContent(text);
            return {
                success: true,
                data: result,
            };
        }
        catch (error) {
            throw new common_1.HttpException(error.message || 'Content extraction failed', error.status || common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
};
exports.MeetingController = MeetingController;
__decorate([
    (0, common_1.Post)('process'),
    (0, common_1.UseInterceptors)((0, platform_express_1.FilesInterceptor)('files', 2)),
    __param(0, (0, common_1.UploadedFiles)()),
    __param(1, (0, common_1.Body)()),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Array, process_meeting_dto_1.ProcessMeetingDto]),
    __metadata("design:returntype", Promise)
], MeetingController.prototype, "processMeeting", null);
__decorate([
    (0, common_1.Post)('speech-to-text'),
    (0, common_1.UseInterceptors)((0, platform_express_1.FileInterceptor)('audio')),
    __param(0, (0, common_1.UploadedFile)()),
    __param(1, (0, common_1.Body)('language')),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, String]),
    __metadata("design:returntype", Promise)
], MeetingController.prototype, "speechToText", null);
__decorate([
    (0, common_1.Post)('clean'),
    __param(0, (0, common_1.Body)('text')),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [String]),
    __metadata("design:returntype", Promise)
], MeetingController.prototype, "cleanText", null);
__decorate([
    (0, common_1.Post)('summarize'),
    __param(0, (0, common_1.Body)('text')),
    __param(1, (0, common_1.Body)('language')),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [String, String]),
    __metadata("design:returntype", Promise)
], MeetingController.prototype, "summarizeText", null);
__decorate([
    (0, common_1.Post)('diarize'),
    __param(0, (0, common_1.Body)('text')),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [String]),
    __metadata("design:returntype", Promise)
], MeetingController.prototype, "diarizeText", null);
__decorate([
    (0, common_1.Post)('extract'),
    __param(0, (0, common_1.Body)('text')),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [String]),
    __metadata("design:returntype", Promise)
], MeetingController.prototype, "extractContent", null);
exports.MeetingController = MeetingController = __decorate([
    (0, common_1.Controller)('meeting'),
    __metadata("design:paramtypes", [ai_service_1.AiService])
], MeetingController);
//# sourceMappingURL=meeting.controller.js.map