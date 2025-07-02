# Bot Cliente Manager

## Overview

This is a Flask-based client management system designed to help manage IPTV and VPN clients with automated WhatsApp reminders. The application provides a web interface for managing clients, message templates, and WhatsApp integration for sending payment reminders.

## System Architecture

The application follows a traditional Flask MVC pattern with the following architectural decisions:

### Backend Architecture
- **Flask Framework**: Chosen for its simplicity and rapid development capabilities
- **File-based Storage**: Uses GitHub repository as a storage backend instead of traditional databases
- **Background Scheduling**: APScheduler for handling automated reminder tasks
- **Modular Design**: Separated concerns with distinct modules for routes, models, storage, and integrations

### Frontend Architecture
- **Server-side Rendering**: Uses Jinja2 templates for dynamic content generation
- **Bootstrap 5**: Provides responsive UI components with dark theme
- **Chart.js**: For dashboard analytics and data visualization
- **Progressive Enhancement**: JavaScript adds interactivity to base HTML functionality

## Key Components

### Core Application (`app.py`, `main.py`)
- Flask application initialization with secret key management
- APScheduler setup for background tasks
- ProxyFix middleware for deployment behind reverse proxies
- Graceful scheduler shutdown handling

### Data Models (`models.py`)
- **Client Model**: Manages client information including payment details and reminder preferences
- **MessageTemplate Model**: Handles customizable message templates for different reminder types
- Serialization methods for data persistence

### Storage Layer (`github_storage.py`)
- **GitHubStorage Class**: Implements file-based storage using GitHub API
- Base64 encoding/decoding for file content management
- Error handling for API communication
- Token-based authentication with GitHub

### Reminder System (`reminder_scheduler.py`)
- Automated scheduling of payment reminders
- Template-based message generation with placeholder substitution
- Integration with WhatsApp messaging service
- Configurable reminder timing (3 days before payment, payment day)

### WhatsApp Integration (`whatsapp_integration.py`)
- QR code generation for WhatsApp Web connection
- Connection status management
- Message sending functionality (framework prepared for actual implementation)

### Web Interface (`routes.py`, `templates/`)
- Dashboard with client statistics and revenue tracking
- Client management (CRUD operations)
- Message template management
- WhatsApp connection interface
- Form validation and error handling

## Data Flow

1. **Client Management**: Users add/edit clients through web forms → Data validated and stored via GitHubStorage
2. **Reminder Scheduling**: Scheduler calculates reminder times based on client payment days → Creates cron jobs
3. **Message Delivery**: Scheduled jobs trigger → Template processing → WhatsApp message sending
4. **Dashboard Updates**: Real-time statistics calculated from stored client data

## External Dependencies

### Storage
- **GitHub API**: Used as the primary data storage backend
- **Repository**: `JeffiBR/Clientes` for data persistence

### Frontend Libraries
- **Bootstrap 5.3.0**: UI framework with dark theme support
- **Bootstrap Icons**: Icon library for consistent UI elements
- **Chart.js**: Data visualization for dashboard analytics

### Python Dependencies
- **Flask**: Web framework and templating
- **APScheduler**: Background task scheduling
- **Requests**: HTTP client for GitHub API communication
- **QRCode**: QR code generation for WhatsApp integration

### WhatsApp Integration
- Currently implements QR code generation framework
- Prepared for WhatsApp Web API integration
- Phone number validation for international format

## Deployment Strategy

### Development
- Flask development server with debug mode
- Environment variable configuration for secrets
- Local file system fallback for GitHub token

### Production Considerations
- ProxyFix middleware configured for reverse proxy deployment
- Session secret key from environment variables
- Error logging configured for debugging
- Background scheduler with graceful shutdown

### Configuration
- GitHub token and repository settings
- WhatsApp integration credentials (when implemented)
- Reminder timing configurations
- Message template defaults

## User Preferences

Preferred communication style: Simple, everyday language.

## Changelog

Changelog:
- July 02, 2025. Initial setup