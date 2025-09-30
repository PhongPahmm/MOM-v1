import { Module } from '@nestjs/common';
import { MeetingController } from './meeting.controller';
import { AiModule } from '../ai/ai.module';

@Module({
  imports: [AiModule],
  controllers: [MeetingController],
})
export class MeetingModule {}
