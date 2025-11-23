import asyncio
import os
import threading
from flask import Flask, request, jsonify, send_file, abort
from config import Config
from telegram_service import telegram_service

app = Flask(__name__)

# Global event loop for async operations
loop = None

def run_async(coro):
    """Helper function to run async code in sync context"""
    global loop
    if loop is None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Initialize telegram service in the background
        def init_telegram():
            try:
                loop.run_until_complete(telegram_service.initialize())
            except Exception as e:
                pass
        
        init_thread = threading.Thread(target=init_telegram)
        init_thread.daemon = True
        init_thread.start()
        init_thread.join()
    
    try:
        return loop.run_until_complete(coro)
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}

@app.route('/')
def home():
    """Health check endpoint"""
    bot_stats = telegram_service.get_bot_stats()
    return jsonify({
        "message": "Leak Data Web API is running",
        "bots": bot_stats,
        "endpoints": {
            "/login": "Query login data - /login?user=username",
            "/pass": "Query password data - /pass?pass=password", 
            "/mail": "Query email data - /mail?mail=email",
            "/stats": "Get bot statistics - /stats"
        }
    })

@app.route('/login', methods=['GET'])
def login_endpoint():
    """
    Login data query endpoint
    Usage: /login?user=username
    """
    username = request.args.get('user')
    
    if not username:
        return jsonify({
            "success": False,
            "message": "Missing 'user' parameter"
        }), 400
    
    try:
        # Run the async query
        result = run_async(telegram_service.query_login(username))
        
        if result["success"]:
            response_data = {
                "success": True,
                "message": result.get("message", "Query completed"),
            }
            
            # Add count if available
            if "count" in result:
                response_data["count"] = result["count"]
            
            # Add file info if available
            if "file_info" in result:
                file_info = result["file_info"]
                response_data["file"] = {
                    "filename": file_info.get("display_name", file_info["original_filename"]),
                    "download_url": file_info["download_url"],
                    "size": file_info.get("file_size", 0)
                }
                
                # Add entries count if available (for data extracted from messages)
                if "entries_count" in file_info:
                    response_data["entries_in_file"] = file_info["entries_count"]
            
            return jsonify(response_data)
        else:
            return jsonify({
                "success": False,
                "message": result.get("message", "No result found")
            }), 404
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}"
        }), 500

@app.route('/pass', methods=['GET'])
def password_endpoint():
    """
    Password data query endpoint
    Usage: /pass?pass=username
    """
    username = request.args.get('pass')
    
    if not username:
        return jsonify({
            "success": False,
            "message": "Missing 'pass' parameter"
        }), 400
    
    try:
        result = run_async(telegram_service.query_password(username))
        
        if result["success"]:
            response_data = {
                "success": True,
                "message": result.get("message", "Query completed"),
            }
            
            # Add count if available
            if "count" in result:
                response_data["count"] = result["count"]
            
            # Add file info if available
            if "file_info" in result:
                file_info = result["file_info"]
                response_data["file"] = {
                    "filename": file_info.get("display_name", file_info["original_filename"]),
                    "download_url": file_info["download_url"],
                    "size": file_info.get("file_size", 0)
                }
                
                # Add entries count if available (for data extracted from messages)
                if "entries_count" in file_info:
                    response_data["entries_in_file"] = file_info["entries_count"]
            
            return jsonify(response_data)
        else:
            return jsonify({
                "success": False,
                "message": result.get("message", "No result found")
            }), 404
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}"
        }), 500

@app.route('/mail', methods=['GET'])
def mail_endpoint():
    """
    Email data query endpoint
    Usage: /mail?mail=email
    """
    email = request.args.get('mail')
    
    if not email:
        return jsonify({
            "success": False,
            "message": "Missing 'mail' parameter (email address)"
        }), 400
    
    try:
        # Run the async query
        result = run_async(telegram_service.query_mail(email))
        
        if result["success"]:
            response_data = {
                "success": True,
                "message": result.get("message", "Query completed"),
            }
            
            # Add count if available
            if "count" in result:
                response_data["count"] = result["count"]
            
            # Add file info if available
            if "file_info" in result:
                file_info = result["file_info"]
                response_data["file"] = {
                    "filename": file_info.get("display_name", file_info["original_filename"]),
                    "download_url": file_info["download_url"],
                    "size": file_info.get("file_size", 0)
                }
                
                # Add entries count if available (for data extracted from messages)
                if "entries_count" in file_info:
                    response_data["entries_in_file"] = file_info["entries_count"]
            
            return jsonify(response_data)
        else:
            return jsonify({
                "success": False,
                "message": result.get("message", "No result found")
            }), 404
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Internal server error: {str(e)}"
        }), 500

@app.route('/download/<filename>')
def download_file(filename):
    """
    File download endpoint
    """
    try:
        file_path = os.path.join(Config.DOWNLOAD_FOLDER, filename)
        
        if not os.path.exists(file_path):
            abort(404)
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error downloading file: {str(e)}"
        }), 500

@app.route('/files')
def list_files():
    """
    List all downloaded files with deletion schedule info
    """
    try:
        if not os.path.exists(Config.DOWNLOAD_FOLDER):
            return jsonify({
                "success": True,
                "files": [],
                "auto_deletion_info": run_async(telegram_service.get_file_deletion_info())
            })
        
        files = []
        for filename in os.listdir(Config.DOWNLOAD_FOLDER):
            file_path = os.path.join(Config.DOWNLOAD_FOLDER, filename)
            if os.path.isfile(file_path):
                # Check if file is scheduled for deletion
                scheduled_for_deletion = filename in telegram_service.file_deletion_timers
                
                files.append({
                    "filename": filename,
                    "download_url": f"{Config.BASE_URL}/download/{filename}",
                    "size": os.path.getsize(file_path),
                    "scheduled_for_deletion": scheduled_for_deletion,
                    "auto_delete_in_minutes": 10 if scheduled_for_deletion else None
                })
        
        return jsonify({
            "success": True,
            "files": files,
            "auto_deletion_info": telegram_service.get_file_deletion_info()
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error listing files: {str(e)}"
        }), 500

@app.route('/files/<filename>/cancel-deletion', methods=['POST'])
def cancel_file_deletion(filename):
    """
    Cancel auto-deletion for a specific file
    """
    try:
        success = telegram_service.cancel_file_deletion(filename)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Auto-deletion cancelled for {filename}"
            })
        else:
            return jsonify({
                "success": False,
                "message": f"No deletion scheduled for {filename}"
            }), 404
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error cancelling deletion: {str(e)}"
        }), 500

@app.route('/stats')
def stats():
    """Get bot usage statistics"""
    try:
        bot_stats = telegram_service.get_bot_stats()
        return jsonify({
            "success": True,
            "stats": bot_stats
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error getting stats: {str(e)}"
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "message": "Endpoint not found"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "message": "Internal server error"
    }), 500

if __name__ == '__main__':
    Config.create_download_dir()
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG
    )