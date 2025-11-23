import asyncio
import os
import re
import threading
import time
from typing import Optional, Dict, Any
from telethon import TelegramClient
from telethon.types import Message, DocumentAttributeFilename
import aiofiles
from config import Config

class TelegramService:
    def __init__(self):
        self.client = None
        self.bot_entities = {}
        self.bot_entity = None
        self.file_deletion_timers = {}
        self.current_bot_index = 0
        self.bot_request_counts = {}
        self.lock = threading.Lock()
        
    def _schedule_file_deletion(self, file_path: str, filename: str):
        def delete_file():
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                if filename in self.file_deletion_timers:
                    del self.file_deletion_timers[filename]
            except Exception as e:
                pass
        
        if filename in self.file_deletion_timers:
            self.file_deletion_timers[filename].cancel()
        
        timer = threading.Timer(600, delete_file)
        timer.daemon = True
        timer.start()
        self.file_deletion_timers[filename] = timer
        
    async def initialize(self):
        try:
            self.client = TelegramClient(
                Config.SESSION_NAME,
                Config.TELEGRAM_API_ID,
                Config.TELEGRAM_API_HASH
            )
            
            await self.client.start(phone=Config.TELEGRAM_PHONE)
            
            for bot_username in Config.BOT_USERNAMES:
                try:
                    entity = await self.client.get_entity(bot_username)
                    self.bot_entities[bot_username] = entity
                    self.bot_request_counts[bot_username] = 0
                except Exception as e:
                    pass
            
            if not self.bot_entities:
                return False
            
            self.bot_entity = list(self.bot_entities.values())[0]
            return True
            
        except Exception as e:
            return False
    
    def _get_next_bot(self):
        with self.lock:
            if not self.bot_entities:
                return None, None
            
            bot_usernames = list(self.bot_entities.keys())
            selected_bot = bot_usernames[self.current_bot_index % len(bot_usernames)]
            self.current_bot_index += 1
            self.bot_request_counts[selected_bot] += 1
            
            return selected_bot, self.bot_entities[selected_bot]
    
    async def send_command_and_wait(self, command: str, query_type: str = "search", search_term: str = "", timeout: int = 30) -> Dict[str, Any]:
        try:
            if not self.client or not self.bot_entities:
                return {
                    "success": False,
                    "message": "Telegram client not initialized"
                }
            
            bot_username, bot_entity = self._get_next_bot()
            if not bot_entity:
                return {
                    "success": False,
                    "message": "No bots available"
                }
            
            await self.client.send_message(bot_entity, command)
            response_data = await self._wait_for_bot_response(timeout, query_type, search_term, bot_entity)
            
            return response_data
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Error sending command: {str(e)}"
            }
    
    async def _wait_for_bot_response(self, timeout: int, query_type: str = "search", search_term: str = "", bot_entity=None) -> Dict[str, Any]:
        try:
            if bot_entity is None:
                bot_entity = self.bot_entity
            
            max_attempts = 8
            messages = []
            for attempt in range(max_attempts):
                await asyncio.sleep(0.5)
                
                messages = []
                async for message in self.client.iter_messages(bot_entity, limit=10):
                    if message.date and (message.date.timestamp() > (asyncio.get_event_loop().time() - timeout)):
                        messages.append(message)
                
                if messages and (any(m.text for m in messages[:3]) or any(m.document for m in messages[:3])):
                    break
            
            messages.sort(key=lambda x: x.date, reverse=True)
            
            if not messages:
                return {
                    "success": False,
                    "message": "No response received from bot"
                }
            
            latest_text_message = None
            latest_file_message = None
            
            for message in messages[:5]:
                if message.text and not latest_text_message:
                    latest_text_message = message
                if message.document and not latest_file_message:
                    latest_file_message = message
                if latest_text_message and latest_file_message:
                    break
            
            latest_message = latest_text_message if latest_text_message else messages[0]
            
            if latest_message.text and ("no found" in latest_message.text.lower() or "❌" in latest_message.text):
                return {
                    "success": False,
                    "message": "Not found ❌"
                }
            
            if latest_message.text:
                found_match_file = re.search(r'found[:\s]+(\d+)\s+strings?', latest_message.text.lower())
                found_match_data = re.search(r'found[:\s]+(\d+)\s+password\(?s?\)?', latest_message.text.lower())
                
                if found_match_file:
                    count = int(found_match_file.group(1))
                    
                    if not latest_file_message:
                        for poll_attempt in range(4):
                            await asyncio.sleep(0.5)
                            updated_messages = []
                            async for message in self.client.iter_messages(self.bot_entity, limit=10):
                                if message.date and (message.date.timestamp() > (asyncio.get_event_loop().time() - timeout)):
                                    updated_messages.append(message)
                            
                            if any(m.document for m in updated_messages[:3]):
                                messages = updated_messages
                                break
                    
                    updated_messages = messages if latest_file_message else messages
                    updated_messages.sort(key=lambda x: x.date, reverse=True)
                    
                    file_info = await self._find_file_in_messages(updated_messages, query_type, search_term, bot_entity)
                    
                    if file_info:
                        return {
                            "success": True,
                            "message": f"Found {count} entries",
                            "count": count,
                            "file_info": file_info
                        }
                    else:
                        return {
                            "success": True,
                            "message": f"Found {count} entries but no file received",
                            "count": count
                        }
                
                elif found_match_data:
                    count = int(found_match_data.group(1))
                    
                    if self._has_data_in_message(latest_message.text):
                        file_info = await self._create_file_from_message(latest_message.text, query_type, search_term, count)
                        
                        if file_info:
                            return {
                                "success": True,
                                "message": f"Found {count} entries",
                                "count": count,
                                "file_info": file_info
                            }
                    
                    return {
                        "success": True,
                        "message": f"Found {count} entries but no data received",
                        "count": count
                    }
            
            return {
                "success": True,
                "message": latest_message.text or "Response received",
                "raw_response": latest_message.text
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Error processing bot response: {str(e)}"
            }
    
    def _has_data_in_message(self, message_text: str) -> bool:
        if not message_text:
            return False
        
        lines = message_text.strip().split('\n')
        data_lines = 0
        found_line = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if re.search(r'found[:\s]+\d+\s+(?:strings?|password\(?s?\)?)', line.lower()) or line.startswith('✅'):
                found_line = True
                continue
            
            if found_line and line and not line.startswith('✅') and not line.startswith('/'):
                data_lines += 1
        
        return data_lines >= 1
    
    async def _create_file_from_message(self, message_text: str, query_type: str, search_term: str, count: int) -> Optional[Dict[str, Any]]:
        try:
            if not message_text:
                return None
            
            lines = message_text.strip().split('\n')
            data_lines = []
            found_line = False
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if (re.search(r'found[:\s]+\d+\s+(?:strings?|password\(?s?\)?)', line.lower()) or 
                    line.startswith('✅') or line.startswith('❌')):
                    found_line = True
                    continue
                
                if found_line and line and not line.startswith('/'):
                    data_lines.append(line)
            
            if not data_lines:
                return None
            
            clean_search_term = re.sub(r'[^\w\s.-]', '', search_term).strip()
            clean_search_term = re.sub(r'[-\s]+', '_', clean_search_term)
            
            if query_type == "login" and clean_search_term:
                new_filename = f"{clean_search_term}.txt"
            elif query_type == "password" and clean_search_term:
                new_filename = f"{clean_search_term}_pass.txt"
            elif query_type == "mail" and clean_search_term:
                new_filename = f"{clean_search_term}_mail.txt"
            else:
                new_filename = "data.txt"
            
            Config.create_download_dir()
            
            timestamp = str(int(asyncio.get_event_loop().time()))
            safe_filename = f"{timestamp}_{new_filename}"
            file_path = os.path.join(Config.DOWNLOAD_FOLDER, safe_filename)
            
            file_content = f"# Search: {search_term}\n"
            file_content += f"# Query type: {query_type}\n"
            file_content += f"# Found: {count} entries\n"
            file_content += f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            file_content += '\n'.join(data_lines)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
            
            file_size = os.path.getsize(file_path)
            self._schedule_file_deletion(file_path, safe_filename)
            download_url = f"{Config.BASE_URL}/download/{safe_filename}"
            
            return {
                "filename": safe_filename,
                "original_filename": new_filename,
                "display_name": new_filename,
                "file_path": file_path,
                "download_url": download_url,
                "file_size": file_size,
                "search_term": search_term,
                "query_type": query_type,
                "entries_count": len(data_lines)
            }
            
        except Exception as e:
            return None
    
    async def _find_file_in_messages(self, messages, query_type: str = "search", search_term: str = "", bot_entity=None) -> Optional[Dict[str, Any]]:
        try:
            for message in messages:
                if message.text and not message.document:
                    continue
                    
                if message.document:
                    original_filename = "downloaded_file.txt"
                    if message.document.attributes:
                        for attr in message.document.attributes:
                            if isinstance(attr, DocumentAttributeFilename):
                                original_filename = attr.file_name
                                break
                    
                    clean_search_term = re.sub(r'[^\w\s-]', '', search_term).strip()
                    clean_search_term = re.sub(r'[-\s]+', '_', clean_search_term)
                    
                    if query_type == "login" and clean_search_term:
                        new_filename = f"{clean_search_term}.txt"
                    elif query_type == "password" and clean_search_term:
                        new_filename = f"{clean_search_term}_pass.txt"
                    elif query_type == "mail" and clean_search_term:
                        new_filename = f"{clean_search_term}_mail.txt"
                    else:
                        new_filename = original_filename
                    
                    Config.create_download_dir()
                    
                    timestamp = str(int(asyncio.get_event_loop().time()))
                    safe_filename = f"{timestamp}_{new_filename}"
                    file_path = os.path.join(Config.DOWNLOAD_FOLDER, safe_filename)
                    
                    temp_path = file_path + ".tmp"
                    await self.client.download_media(message.document, temp_path)
                    
                    try:
                        with open(temp_path, 'r', encoding='utf-8', errors='ignore') as temp_file:
                            original_content = temp_file.read()
                        
                        with open(file_path, 'w', encoding='utf-8') as final_file:
                            final_file.write(f"# Search: {search_term}\n")
                            final_file.write(f"# Query type: {query_type}\n")
                            final_file.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                            final_file.write(original_content)
                        
                        os.remove(temp_path)
                    except Exception as e:
                        if os.path.exists(temp_path):
                            os.rename(temp_path, file_path)
                    
                    self._schedule_file_deletion(file_path, safe_filename)
                    download_url = f"{Config.BASE_URL}/download/{safe_filename}"
                    
                    return {
                        "filename": safe_filename,
                        "original_filename": original_filename,
                        "display_name": new_filename,
                        "file_path": file_path,
                        "download_url": download_url,
                        "file_size": message.document.size,
                        "search_term": search_term,
                        "query_type": query_type
                    }
            
            return None
            
        except Exception as e:
            return None
    
    async def query_login(self, username: str) -> Dict[str, Any]:
        command = f"/login {username}"
        return await self.send_command_and_wait(command, "login", username)
    
    async def query_password(self, username: str) -> Dict[str, Any]:
        command = f"/password {username}"
        return await self.send_command_and_wait(command, "password", username)
    
    async def query_mail(self, email: str) -> Dict[str, Any]:
        command = f"/mail {email}"
        return await self.send_command_and_wait(command, "mail", email)
    
    def cancel_file_deletion(self, filename: str) -> bool:
        if filename in self.file_deletion_timers:
            self.file_deletion_timers[filename].cancel()
            del self.file_deletion_timers[filename]
            return True
        return False
    
    def get_file_deletion_info(self) -> Dict[str, Any]:
        return {
            "files_scheduled_for_deletion": len(self.file_deletion_timers),
            "filenames": list(self.file_deletion_timers.keys())
        }
    
    def get_bot_stats(self) -> Dict[str, Any]:
        return {
            "total_bots": len(self.bot_entities),
            "available_bots": list(self.bot_entities.keys()),
            "request_counts": self.bot_request_counts,
            "total_requests": sum(self.bot_request_counts.values())
        }
    
    async def close(self):
        for timer in self.file_deletion_timers.values():
            timer.cancel()
        self.file_deletion_timers.clear()
        
        if self.client:
            await self.client.disconnect()

telegram_service = TelegramService()