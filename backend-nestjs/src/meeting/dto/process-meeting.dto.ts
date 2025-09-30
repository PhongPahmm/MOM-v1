import { IsOptional, IsString } from 'class-validator';

export class ProcessMeetingDto {
  @IsOptional()
  @IsString()
  language?: string = 'vi';
}
