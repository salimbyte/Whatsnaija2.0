# Whatsnaija - Community Discussion Platform

A Django-based community discussion platform similar to Reddit, featuring posts, comments, stages (stages), and user profiles.

## Features

- **User Authentication**: Registration, login, logout, and profile management
- **Posts**: Create, edit, delete posts with rich text editor (CKEditor)
- **Comments**: Nested comments with like functionality
- **Stages**: stages/forums for organizing content
- **Likes/Dislikes**: Vote on posts and comments
- **Tags**: Categorize posts with tags
- **Image Uploads**: Support for post images and user avatars
- **Responsive Design**: Mobile-friendly interface

## Project Structure

```
vaze/
├── comments/          # Comment models and logic
├── moderations/       # Moderation features
├── posts/            # Post models, views, and forms
├── stages/           # Stage (community) management
├── static/           # Static files (CSS, JS, images)
│   ├── style/
│   ├── scripts/
│   └── images/
├── templates/        # HTML templates
├── users/            # User authentication and profiles
├── vaze/            # Main project configuration
│   ├── settings_base.py  # Base settings
│   └── settings.py       # Environment-specific settings
├── manage.py
└── requirements.txt
```

## Setup Instructions

### 1. Clone and Setup Virtual Environment

```bash
cd /home/salim/vaze

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Linux/Mac
# or
venv\Scripts\activate  # On Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Configuration

Create a `.env` file in the project root (copy from `.env.example`):

```bash
cp .env.example .env
```

Edit `.env` and update:
- `SECRET_KEY`: Generate a new secret key for production
- `DEBUG`: Set to `False` for production
- `ALLOWED_HOSTS`: Add your domain names

### 4. Database Setup

```bash
# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### 5. Collect Static Files

```bash
python manage.py collectstatic --noinput
```

### 6. Run Development Server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000` in your browser.

## Important Notes

### Security
- The `SECRET_KEY` is currently exposed in `settings_base.py`. **Change this immediately** for production!
- Set `DEBUG = False` in production
- Configure proper `ALLOWED_HOSTS` for production
- Use environment variables for sensitive data

### Database
- Currently using SQLite (suitable for development)
- For production, consider PostgreSQL or MySQL

### Media Files
- User uploads are stored in `media/` directory
- Make sure this directory is writable
- Configure proper backup strategy for production

### File Changes Summary

#### Models Fixed:
- **users/models.py**: Fixed typo `is_varified` → `is_verified`, added proper signals for profile creation
- **posts/models.py**: Fixed `created_at` field (auto_now → auto_now_add), added slug auto-generation, renamed `PostImages` → `PostImage`
- **stages/models.py**: Added description field, proper timestamps, is_active flag
- **comments/models.py**: Fixed imports, improved relationships

#### Views Refactored:
- **users/views.py**: Using Django forms, proper error handling, login_required decorators
- **posts/views.py**: Cleaner structure, proper permissions checking, improved queries
- **vaze/views.py**: Added query optimization with select_related, proper filtering

#### Forms Created:
- **users/forms.py**: Registration, login, profile forms
- **posts/forms.py**: Post and image upload forms
- **comments/forms.py**: Comment form
- **stages/forms.py**: Stage creation form

#### URLs Reorganized:
- Added `app_name` to URL configs for namespacing
- Separated profile URLs to avoid conflicts
- Consistent naming conventions

#### Settings Improved:
- Split into `settings_base.py` and `settings.py`
- Better organization of installed apps
- Proper static/media configuration
- Security improvements

#### CSS Optimized:
- Removed duplicate font declarations
- Cleaned up commented code
- Better organization
- Improved responsiveness

#### Templates Enhanced:
- Proper use of Django template tags
- Added user authentication checks
- Cleaned up script duplications
- Better semantic HTML

## Admin Panel

Access the admin panel at `http://127.0.0.1:8000/admin/`

Use the superuser credentials you created during setup.

## Development

### Running Tests

```bash
python manage.py test
```

### Creating Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Seed Database (for testing)

```bash
python manage.py seed posts --number=50
python manage.py seed users --number=20
```

## Production Deployment

1. Set `DEBUG = False` in settings
2. Configure proper database (PostgreSQL recommended)
3. Set up proper web server (Gunicorn + Nginx)
4. Configure HTTPS/SSL certificates
5. Set up proper logging
6. Configure email backend for notifications
7. Set up regular backups
8. Configure CDN for static files

## License

This project is for educational purposes.

## Support

For issues and questions, please create an issue in the repository.
