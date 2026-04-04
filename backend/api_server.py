"""
Flask API Server for Material Processing Pipeline

Provides REST API and Server-Sent Events for real-time progress updates
"""

import sys
import os
import logging
from pathlib import Path
import json
import threading
import time
from typing import Dict, Any, Optional
from queue import Queue

from flask import Flask, jsonify, request, Response
from flask_cors import CORS

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))

# Import quiet module first to initialize logging configuration
from core.quiet import quiet_print  # noqa: F401 — triggers logging.basicConfig

logger = logging.getLogger('transcriptor.api')

from core.config_loader import load_config, PipelineConfig
from core.processing_calculator import ProcessingCalculator
from core.quiet import set_log_callback
from process_v2 import MaterialProcessor

# Global state
processing_lock = threading.Lock()
current_process = None
progress_queue = Queue()
current_status = {
    'running': False,
    'progress': 0,
    'total': 0,
    'stats': {
        'audio_processed': 0,
        'videos_processed': 0,
        'pdfs_processed': 0,
        'images_processed': 0,
        'documents_processed': 0,
        'errors': 0
    },
    'logs': []
}

app = Flask(__name__)
CORS(app)


def log_message(message: str, level: str = 'INFO'):
    """Add a log message to the current status"""
    timestamp = time.strftime('%H:%M:%S')
    log_entry = {
        'timestamp': timestamp,
        'level': level,
        'message': message
    }
    current_status['logs'].append(log_entry)
    progress_queue.put({'type': 'log', 'data': log_entry})


class ProgressProcessor(MaterialProcessor):
    """Extended processor that reports progress via API"""

    def _process_file_wrapper(self, file_path: Path, file_type: str, output_dir: Path):
        result = super()._process_file_wrapper(file_path, file_type, output_dir)

        with processing_lock:
            current_status['progress'] += 1
            current_status['stats'] = dict(self.stats)

        progress_queue.put({
            'type': 'progress',
            'data': {
                'current': current_status['progress'],
                'total': current_status['total'],
                'stats': current_status['stats']
            }
        })

        return result


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    try:
        config_path = Path('.pipeline_settings.json')
        if config_path.exists():
            with open(config_path, 'r') as f:
                config_data = json.load(f)
        else:
            config = load_config(str(config_path))
            config_data = config.to_dict()

        return jsonify({'success': True, 'config': config_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration"""
    try:
        config_data = request.json
        config_path = Path('.pipeline_settings.json')

        if config_path.exists():
            with open(config_path, 'r') as f:
                existing = json.load(f)
        else:
            existing = {}

        existing.update(config_data)

        with open(config_path, 'w') as f:
            json.dump(existing, f, indent=2)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/preflight', methods=['POST'])
def run_preflight():
    """Run preflight estimation"""
    try:
        config_data = request.json

        config = load_config('.pipeline_settings.json')
        if config_data:
            for key, value in config_data.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        source_dir = Path(config_data.get('source_directory', config.source_directory))

        processor = MaterialProcessor(config)
        processor.source_dir = source_dir.resolve()
        materials = processor.find_materials(source_dir)

        total_files = sum(len(files) for files in materials.values())
        if total_files == 0:
            return jsonify({
                'success': True,
                'total_files': 0,
                'message': 'No files found to process'
            })

        calculator = ProcessingCalculator(config.whisper_model)
        estimates = calculator.calculate_all(materials)

        return jsonify({
            'success': True,
            'total_files': total_files,
            'estimates': {
                'audio': {
                    'count': len(materials['audio']),
                    'duration': estimates['audio']['total_duration_minutes'],
                    'processing_time': estimates['audio']['processing_time_minutes']
                },
                'videos': {
                    'count': len(materials['videos']),
                    'duration': estimates['videos']['total_duration_minutes'],
                    'processing_time': estimates['videos']['processing_time_minutes']
                },
                'pdfs': {
                    'count': len(materials['pdfs']),
                    'processing_time': estimates['pdfs']['processing_time_minutes']
                },
                'images': {
                    'count': len(materials['images']),
                    'processing_time': estimates['images']['processing_time_minutes']
                },
                'documents': {
                    'count': len(materials['documents']),
                    'processing_time': estimates['documents']['processing_time_minutes']
                },
                'total_time': estimates['totals']['total_time_minutes']
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/start', methods=['POST'])
def start_processing():
    """Start processing pipeline"""
    global current_process

    with processing_lock:
        if current_status['running']:
            return jsonify({'success': False, 'error': 'Processing already running'}), 400

    try:
        config_data = request.json or {}
        config = load_config('.pipeline_settings.json')

        for key, value in config_data.items():
            if hasattr(config, key):
                setattr(config, key, value)

        source_dir = Path(config_data.get('source_directory', config.source_directory))
        output_dir = Path(config_data.get('output_directory', config.output_directory))

        with processing_lock:
            current_status['running'] = True
            current_status['progress'] = 0
            current_status['total'] = 0
            current_status['stats'] = {
                'audio_processed': 0,
                'videos_processed': 0,
                'pdfs_processed': 0,
                'images_processed': 0,
                'documents_processed': 0,
                'errors': 0
            }
            current_status['logs'] = []

            while not progress_queue.empty():
                progress_queue.get()

        def process_thread():
            global current_process
            try:
                set_log_callback(log_message)
                log_message('Starting material processing...', 'INFO')

                processor = ProgressProcessor(config)
                processor.source_dir = source_dir.resolve()

                materials = processor.find_materials(source_dir)
                total_files = sum(len(files) for files in materials.values())

                with processing_lock:
                    current_status['total'] = total_files

                log_message(f'Found {total_files} files to process', 'INFO')

                if total_files == 0:
                    log_message('No files to process', 'WARN')
                    with processing_lock:
                        current_status['running'] = False
                    return

                output_dir.mkdir(parents=True, exist_ok=True)
                processor.process_all(source_dir, output_dir)
                log_message('Processing complete!', 'SUCCESS')

            except Exception as e:
                log_message(f'Error during processing: {str(e)}', 'ERROR')
            finally:
                set_log_callback(None)
                with processing_lock:
                    current_status['running'] = False
                progress_queue.put({'type': 'complete', 'data': current_status['stats']})

        thread = threading.Thread(target=process_thread, daemon=True)
        thread.start()
        current_process = thread

        return jsonify({'success': True})

    except Exception as e:
        with processing_lock:
            current_status['running'] = False
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current processing status"""
    with processing_lock:
        return jsonify({
            'success': True,
            'status': current_status.copy()
        })


@app.route('/api/events', methods=['GET'])
def events():
    """Server-Sent Events endpoint for real-time updates"""
    def event_stream():
        try:
            with processing_lock:
                yield f"data: {json.dumps({'type': 'status', 'data': current_status.copy()})}\n\n"

            while True:
                try:
                    update = progress_queue.get(timeout=1)
                    yield f"data: {json.dumps(update)}\n\n"
                except:
                    with processing_lock:
                        if not current_status['running']:
                            break
                    yield f": heartbeat\n\n"
        except GeneratorExit:
            pass

    return Response(event_stream(), mimetype='text/event-stream')


def main():
    """Start the API server"""
    logger.info("API server starting on http://localhost:5000")
    print("=" * 60)
    print("Material Processing Pipeline - API Server")
    print("=" * 60)
    print("\nServer starting on http://localhost:5000")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)


if __name__ == '__main__':
    main()
