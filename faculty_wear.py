# faculty_wear.py
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from bson import ObjectId
from datetime import datetime
import os
import cloudinary
import cloudinary.uploader
import cloudinary.api
from functools import wraps

faculty_wear_bp = Blueprint('faculty_wear', __name__, url_prefix='/api/faculty-wear')

# Cloudinary configuration (you can also set these in your app config)
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)

# Helper functions
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_faculty_wear_data(data, require_image=False):
    errors = []
    
    if not data.get('title'):
        errors.append('Title is required')
    
    if not data.get('description'):
        errors.append('Description is required')
    
    if not data.get('standard_price'):
        errors.append('Standard price is required')
    elif float(data.get('standard_price', 0)) <= 0:
        errors.append('Standard price must be greater than 0')
    
    if data.get('custom_price') and float(data.get('custom_price', 0)) <= 0:
        errors.append('Custom price must be greater than 0')
    
    if not data.get('order'):
        errors.append('Display order is required')
    elif int(data.get('order', 0)) < 1:
        errors.append('Display order must be at least 1')
    
    return errors

def upload_to_cloudinary(file, folder="faculty_wears"):
    if not file or not allowed_file(file.filename):
        return None
    
    try:
        upload_result = cloudinary.uploader.upload(
            file,
            folder=folder,
            resource_type="auto",
            quality="auto:good",
            width=800,
            crop="limit"
        )
        return upload_result.get('secure_url')
    except Exception as e:
        print(f"Cloudinary upload error: {str(e)}")
        return None

def delete_from_cloudinary(image_url):
    try:
        # Extract public_id from URL
        public_id = image_url.split('/')[-1].split('.')[0]
        if '/' in image_url:
            # Get the full path with folder
            parts = image_url.split('/')
            folder = parts[-2]
            public_id = f"{folder}/{public_id}"
        
        result = cloudinary.uploader.destroy(public_id)
        return result.get('result') == 'ok'
    except Exception as e:
        print(f"Cloudinary delete error: {str(e)}")
        return False

def get_faculty_wear_response(wear):
    return {
        'id': str(wear['_id']),
        'title': wear['title'],
        'description': wear['description'],
        'image_url': wear.get('image_url', ''),
        'badge_text': wear.get('badge_text', ''),
        'standard_price': wear['standard_price'],
        'custom_price': wear.get('custom_price'),
        'add_to_cart_text': wear.get('add_to_cart_text', 'Add to Cart'),
        'add_to_cart_link': wear.get('add_to_cart_link', ''),
        'buy_now_text': wear.get('buy_now_text', 'Buy Now'),
        'buy_now_link': wear.get('buy_now_link', ''),
        'order': wear.get('order', 1),
        'created_at': wear.get('created_at', datetime.now()).isoformat(),
        'updated_at': wear.get('updated_at', datetime.now()).isoformat()
    }

# Routes
@faculty_wear_bp.route('/', methods=['GET'])
def get_all_wears():
    try:
        db = request.app.config['db']
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 5))
        search = request.args.get('search', '').strip()
        
        query = {}
        if search:
            query['$or'] = [
                {'title': {'$regex': search, '$options': 'i'}},
                {'description': {'$regex': search, '$options': 'i'}},
                {'badge_text': {'$regex': search, '$options': 'i'}}
            ]
        
        total = db.faculty_wear.count_documents(query)
        wears = list(db.faculty_wear.find(query)
                    .sort('order', 1)
                    .skip((page - 1) * limit)
                    .limit(limit))
        
        return jsonify({
            'success': True,
            'data': [get_faculty_wear_response(wear) for wear in wears],
            'total': total,
            'page': page,
            'limit': limit
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@faculty_wear_bp.route('/<wear_id>', methods=['GET'])
def get_wear(wear_id):
    try:
        db = request.app.config['db']
        wear = db.faculty_wear.find_one({'_id': ObjectId(wear_id)})
        
        if not wear:
            return jsonify({'success': False, 'error': 'Wear not found'}), 404
        
        return jsonify({
            'success': True,
            'data': get_faculty_wear_response(wear)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@faculty_wear_bp.route('/', methods=['POST'])
def create_wear():
    try:
        db = request.app.config['db']
        
        # Handle form data
        form_data = request.form.to_dict()
        errors = validate_faculty_wear_data(form_data, require_image=True)
        
        if errors:
            return jsonify({'success': False, 'error': 'Validation failed', 'details': errors}), 400
        
        # Handle file upload
        image_file = request.files.get('image')
        if not image_file:
            return jsonify({'success': False, 'error': 'Image is required'}), 400
        
        image_url = upload_to_cloudinary(image_file)
        if not image_url:
            return jsonify({'success': False, 'error': 'Failed to upload image'}), 400
        
        # Prepare wear data
        wear_data = {
            'title': form_data['title'],
            'description': form_data['description'],
            'image_url': image_url,
            'badge_text': form_data.get('badge_text', ''),
            'standard_price': float(form_data['standard_price']),
            'custom_price': float(form_data['custom_price']) if form_data.get('custom_price') else None,
            'add_to_cart_text': form_data.get('add_to_cart_text', 'Add to Cart'),
            'add_to_cart_link': form_data.get('add_to_cart_link', ''),
            'buy_now_text': form_data.get('buy_now_text', 'Buy Now'),
            'buy_now_link': form_data.get('buy_now_link', ''),
            'order': int(form_data.get('order', 1)),
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        
        # Insert into database
        result = db.faculty_wear.insert_one(wear_data)
        wear_data['_id'] = result.inserted_id
        
        return jsonify({
            'success': True,
            'data': get_faculty_wear_response(wear_data),
            'message': 'Faculty wear created successfully'
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@faculty_wear_bp.route('/<wear_id>', methods=['PUT'])
def update_wear(wear_id):
    try:
        db = request.app.config['db']
        
        # Check if wear exists
        existing_wear = db.faculty_wear.find_one({'_id': ObjectId(wear_id)})
        if not existing_wear:
            return jsonify({'success': False, 'error': 'Wear not found'}), 404
        
        # Handle form data
        form_data = request.form.to_dict()
        errors = validate_faculty_wear_data(form_data, require_image=False)
        
        if errors:
            return jsonify({'success': False, 'error': 'Validation failed', 'details': errors}), 400
        
        # Handle file upload if new image is provided
        image_file = request.files.get('image')
        image_url = None
        
        if image_file:
            # First upload new image
            image_url = upload_to_cloudinary(image_file)
            if not image_url:
                return jsonify({'success': False, 'error': 'Failed to upload image'}), 400
            
            # Then delete old image from Cloudinary
            if existing_wear.get('image_url'):
                delete_from_cloudinary(existing_wear['image_url'])
        
        # Prepare update data
        update_data = {
            'title': form_data['title'],
            'description': form_data['description'],
            'badge_text': form_data.get('badge_text', ''),
            'standard_price': float(form_data['standard_price']),
            'custom_price': float(form_data['custom_price']) if form_data.get('custom_price') else None,
            'add_to_cart_text': form_data.get('add_to_cart_text', 'Add to Cart'),
            'add_to_cart_link': form_data.get('add_to_cart_link', ''),
            'buy_now_text': form_data.get('buy_now_text', 'Buy Now'),
            'buy_now_link': form_data.get('buy_now_link', ''),
            'order': int(form_data.get('order', 1)),
            'updated_at': datetime.now()
        }
        
        if image_url:
            update_data['image_url'] = image_url
        
        # Update in database
        db.faculty_wear.update_one(
            {'_id': ObjectId(wear_id)},
            {'$set': update_data}
        )
        
        # Get updated wear
        updated_wear = db.faculty_wear.find_one({'_id': ObjectId(wear_id)})
        
        return jsonify({
            'success': True,
            'data': get_faculty_wear_response(updated_wear),
            'message': 'Faculty wear updated successfully'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@faculty_wear_bp.route('/<wear_id>', methods=['DELETE'])
def delete_wear(wear_id):
    try:
        db = request.app.config['db']
        
        # Check if wear exists
        wear = db.faculty_wear.find_one({'_id': ObjectId(wear_id)})
        if not wear:
            return jsonify({'success': False, 'error': 'Wear not found'}), 404
        
        # Delete image from Cloudinary if exists
        if wear.get('image_url'):
            delete_from_cloudinary(wear['image_url'])
        
        # Delete wear from database
        result = db.faculty_wear.delete_one({'_id': ObjectId(wear_id)})
        
        if result.deleted_count == 0:
            return jsonify({'success': False, 'error': 'Failed to delete wear'}), 500
        
        return jsonify({
            'success': True,
            'message': 'Faculty wear deleted successfully'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def init_faculty_wear_module(app, db):
    """Initialize the faculty wear module with the Flask app"""
    # Register the blueprint
    app.register_blueprint(faculty_wear_bp)
    
    # Configure database
    app.config['db'] = db
    
    # Initialize Cloudinary (if not already initialized)
    if not cloudinary.config().cloud_name:
        cloudinary.config(
            cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
            api_key=os.getenv('CLOUDINARY_API_KEY'),
            api_secret=os.getenv('CLOUDINARY_API_SECRET'),
            secure=True
        )
