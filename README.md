# Cowork System Architecture

## Overview

This document describes the system architecture for the Cowork project, a collaborative workspace environment running on macOS.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Application Layer                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  CLI     │  │  Web UI  │  │  API     │  │  Scripts │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Service Layer                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Auth    │  │  Cache   │  │  Queue   │  │  Logger  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Data Layer                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  SQLite  │  │  Redis   │  │  S3      │  │  Local   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. Application Layer

- **CLI Tool**: Command-line interface for managing workspace operations
- **Web UI**: Browser-based dashboard for monitoring and control
- **API**: RESTful endpoints for external integrations
- **Scripts**: Automation and utility scripts

### 2. Service Layer

- **Authentication**: User management and access control
- **Caching**: Redis-based session and data caching
- **Message Queue**: Background job processing
- **Logging**: Centralized logging and monitoring

### 3. Data Layer

- **SQLite**: Primary database for persistent storage
- **Redis**: In-memory caching and pub/sub
- **S3**: Object storage for files and media
- **Local Storage**: Temporary and cache files

## Technology Stack

| Component | Technology |
|-----------|------------|
| Runtime | Node.js / Python |
| Database | SQLite |
| Cache | Redis |
| Storage | S3 / Local |
| Frontend | React / Vue |
| CLI | TypeScript |

## Directory Structure

```
~/cowork/
├── src/
│   ├── api/
│   ├── cli/
│   ├── services/
│   └── utils/
├── tests/
├── docs/
├── scripts/
├── config/
└── README.md
```

## Deployment

- **Development**: npm run dev
- **Production**: npm run build && npm run start
- **Database**: SQLite (local) / PostgreSQL (production)

## Security

- JWT authentication
- Rate limiting
- Input validation
- Environment variable secrets

## License

MIT
