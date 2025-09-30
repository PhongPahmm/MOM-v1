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
Object.defineProperty(exports, "__esModule", { value: true });
exports.AiService = void 0;
const common_1 = require("@nestjs/common");
const axios_1 = require("@nestjs/axios");
const rxjs_1 = require("rxjs");
const config_1 = require("@nestjs/config");
let AiService = class AiService {
    httpService;
    configService;
    aiServiceUrl;
    constructor(httpService, configService) {
        this.httpService = httpService;
        this.configService = configService;
        this.aiServiceUrl = this.configService.get('AI_SERVICE_URL', 'http://localhost:8001');
    }
    async speechToText(audioFile, language = 'vi') {
        try {
            const formData = new FormData();
            formData.append('audio', new Blob([audioFile.buffer]), audioFile.originalname);
            formData.append('language', language);
            const response = await (0, rxjs_1.firstValueFrom)(this.httpService.post(`${this.aiServiceUrl}/speech-to-text`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            }));
            return response.data;
        }
        catch (error) {
            throw new common_1.HttpException(`Speech-to-text failed: ${error.message}`, common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    async cleanText(text) {
        try {
            const formData = new FormData();
            formData.append('text', text);
            const response = await (0, rxjs_1.firstValueFrom)(this.httpService.post(`${this.aiServiceUrl}/clean`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            }));
            return response.data;
        }
        catch (error) {
            throw new common_1.HttpException(`Text cleaning failed: ${error.message}`, common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    async summarizeText(text, language = 'vi') {
        try {
            const formData = new FormData();
            formData.append('text', text);
            formData.append('language', language);
            const response = await (0, rxjs_1.firstValueFrom)(this.httpService.post(`${this.aiServiceUrl}/summarize`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            }));
            return response.data;
        }
        catch (error) {
            throw new common_1.HttpException(`Summarization failed: ${error.message}`, common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    async diarizeText(text) {
        try {
            const formData = new FormData();
            formData.append('text', text);
            const response = await (0, rxjs_1.firstValueFrom)(this.httpService.post(`${this.aiServiceUrl}/diarize`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            }));
            return response.data;
        }
        catch (error) {
            throw new common_1.HttpException(`Diarization failed: ${error.message}`, common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    async extractContent(text) {
        try {
            const formData = new FormData();
            formData.append('text', text);
            const response = await (0, rxjs_1.firstValueFrom)(this.httpService.post(`${this.aiServiceUrl}/extract`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            }));
            return response.data;
        }
        catch (error) {
            throw new common_1.HttpException(`Content extraction failed: ${error.message}`, common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
    async processFull(audioFile, transcriptFile, language = 'vi') {
        try {
            const formData = new FormData();
            if (audioFile) {
                formData.append('audio', new Blob([audioFile.buffer]), audioFile.originalname);
            }
            else if (transcriptFile) {
                formData.append('transcript', new Blob([transcriptFile.buffer]), transcriptFile.originalname);
            }
            else {
                throw new common_1.HttpException('No input file provided', common_1.HttpStatus.BAD_REQUEST);
            }
            formData.append('language', language);
            const response = await (0, rxjs_1.firstValueFrom)(this.httpService.post(`${this.aiServiceUrl}/process-full`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            }));
            return response.data;
        }
        catch (error) {
            throw new common_1.HttpException(`Full processing failed: ${error.message}`, common_1.HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }
};
exports.AiService = AiService;
exports.AiService = AiService = __decorate([
    (0, common_1.Injectable)(),
    __metadata("design:paramtypes", [axios_1.HttpService,
        config_1.ConfigService])
], AiService);
//# sourceMappingURL=ai.service.js.map