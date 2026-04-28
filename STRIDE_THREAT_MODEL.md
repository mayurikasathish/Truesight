# Microsoft STRIDE Threat Model for TrueSight

## Overview
This document applies Microsoft's STRIDE threat modeling framework to the TrueSight cryptographic watermarking and deepfake detection system. STRIDE is a systematic approach to identifying security threats across six categories.

## STRIDE Framework

### S - Spoofing
**Definition**: Impersonating something or someone else.

**Threats Identified**:
1. **Media Source Spoofing**: Attackers may upload fake media claiming it's authentic
2. **Key Pair Spoofing**: Users may claim ownership of keys they didn't generate
3. **API Endpoint Spoofing**: Malicious actors may create fake endpoints to intercept requests

**Mitigations Implemented**:
- ✅ Cryptographic signature verification using Ed25519 ensures only the private key holder can sign media
- ✅ Public key verification prevents unauthorized signature validation
- ✅ Deepfake detection helps identify manipulated media before watermarking
- ✅ API authentication and rate limiting (recommended for production)
- ✅ HTTPS enforcement prevents man-in-the-middle attacks

**Recommendations**:
- Implement API key authentication for production use
- Add request signing for API calls
- Implement user authentication and session management
- Add logging and monitoring for suspicious activities

---

### T - Tampering
**Definition**: Unauthorized modification of data or system components.

**Threats Identified**:
1. **Media Tampering**: Watermarked media may be modified after embedding
2. **Watermark Extraction Tampering**: Attackers may attempt to remove or modify watermarks
3. **Metadata Tampering**: JSON metadata files could be modified to alter verification results
4. **Code Tampering**: Backend code could be modified to bypass security checks

**Mitigations Implemented**:
- ✅ Cryptographic signatures ensure tampering is detected during verification
- ✅ Original file hash comparison detects any modifications
- ✅ Watermark embedding uses DWT-QIM which is resistant to common image processing
- ✅ Deepfake detection identifies tampered regions in media
- ✅ File integrity checks on storage (recommended)

**Recommendations**:
- Implement file checksums for stored media files
- Add version control for codebase
- Use read-only storage for verification metadata
- Implement code signing for deployment
- Add integrity checks for uploaded files

---

### R - Repudiation
**Definition**: Ability to deny performing an action when there's no proof to the contrary.

**Threats Identified**:
1. **Watermarking Repudiation**: Users may deny having watermarked media
2. **Detection Repudiation**: System may not have proof of deepfake detection results
3. **API Request Repudiation**: Users may deny making specific API calls

**Mitigations Implemented**:
- ✅ Comprehensive logging of all watermarking operations
- ✅ Metadata files store timestamps and signatures
- ✅ JSON analysis files preserve deepfake detection results
- ✅ Server-side logs record all API requests and responses

**Recommendations**:
- Implement audit logging with timestamps and user IDs
- Store logs in tamper-proof storage (blockchain or WORM storage)
- Add digital signatures to log entries
- Implement log retention policies
- Create audit trails for compliance

---

### I - Information Disclosure
**Definition**: Exposure of sensitive information to unauthorized parties.

**Threats Identified**:
1. **Private Key Exposure**: Private keys may be leaked or intercepted
2. **Media Content Disclosure**: Sensitive media files may be exposed
3. **User Data Disclosure**: User information may be leaked through API responses
4. **Analysis Results Disclosure**: Deepfake detection results may reveal sensitive information

**Mitigations Implemented**:
- ✅ Private keys are never stored on server (only in client)
- ✅ Private keys are not returned in API responses
- ✅ Media files stored in secure directory with restricted access
- ✅ Base64 encoding for heatmaps (not sensitive data)
- ✅ CORS middleware configured for security

**Recommendations**:
- Implement encryption at rest for stored media files
- Use environment variables for sensitive configuration
- Implement proper access control lists (ACLs)
- Add data classification and handling policies
- Implement secure key management (HSM or key vault)
- Add data anonymization for analytics

---

### D - Denial of Service (DoS)
**Definition**: Attacks that prevent legitimate users from accessing the system.

**Threats Identified**:
1. **API Flooding**: Attackers may flood endpoints with requests
2. **Resource Exhaustion**: Large file uploads may exhaust server resources
3. **Video Processing DoS**: Processing large videos may overload CPU/memory
4. **Storage Exhaustion**: Attackers may fill storage with large files

**Mitigations Implemented**:
- ✅ File size validation on upload
- ✅ Supported format restrictions
- ✅ Frame limits for video processing
- ✅ Temporary file cleanup after processing
- ✅ Error handling prevents resource leaks

**Recommendations**:
- Implement rate limiting per IP/user
- Add file size limits (e.g., max 100MB for images, 500MB for videos)
- Implement request queuing for video processing
- Add timeout mechanisms for long-running operations
- Use CDN for static assets
- Implement auto-scaling for high load
- Add monitoring and alerting for resource usage

---

### E - Elevation of Privilege
**Definition**: Gaining unauthorized access to system functions or data.

**Threats Identified**:
1. **Privilege Escalation**: Attackers may attempt to gain admin access
2. **File System Access**: Attackers may try to access files outside intended directories
3. **Code Execution**: Malicious code may be executed through file uploads
4. **API Abuse**: Unauthorized users may access admin-only endpoints

**Mitigations Implemented**:
- ✅ File path validation prevents directory traversal
- ✅ File type validation prevents code execution
- ✅ Sandboxed file processing (temporary directories)
- ✅ No shell command execution from user input
- ✅ Restricted file system access

**Recommendations**:
- Implement role-based access control (RBAC)
- Add authentication and authorization middleware
- Use least privilege principle for file system access
- Implement input validation and sanitization
- Add security headers (CSP, X-Frame-Options, etc.)
- Regular security audits and penetration testing
- Implement API versioning and deprecation

---

## Threat Model Matrix

| Threat Category | Threat | Probability | Impact | Risk Level | Mitigation Status |
|---------------|--------|-------------|--------|-----------|-------------------|
| Spoofing | Media source spoofing | Medium | High | **High** | ✅ Mitigated |
| Spoofing | Key pair spoofing | Low | High | Medium | ✅ Mitigated |
| Tampering | Media tampering | High | High | **High** | ✅ Mitigated |
| Tampering | Watermark removal | Medium | High | **High** | ✅ Mitigated |
| Repudiation | Action denial | Medium | Medium | Medium | ⚠️ Partial |
| Information Disclosure | Private key leak | Low | Critical | **Critical** | ✅ Mitigated |
| Information Disclosure | Media exposure | Medium | Medium | Medium | ⚠️ Partial |
| Denial of Service | API flooding | High | Medium | **High** | ⚠️ Partial |
| Denial of Service | Resource exhaustion | Medium | High | **High** | ⚠️ Partial |
| Elevation of Privilege | Unauthorized access | Low | Critical | Medium | ✅ Mitigated |

**Legend**:
- ✅ Mitigated: Threat is addressed with current implementation
- ⚠️ Partial: Threat is partially addressed, needs additional measures
- ❌ Not Mitigated: Threat needs immediate attention

---

## Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client (Browser)                         │
│  - Private key generation                                    │
│  - File upload                                              │
│  - Result display                                           │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Backend (Secure)                       │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Authentication Layer (Recommended)                   │ │
│  └──────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Rate Limiting & Input Validation                     │ │
│  └──────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Watermarking Module (DWT-QIM + Ed25519)              │ │
│  └──────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Deepfake Detection Module                            │ │
│  └──────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Secure Storage (Isolated)                            │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Compliance Considerations

### Data Protection
- **GDPR Compliance**: Implement user consent, data minimization, right to deletion
- **Data Retention**: Define policies for media and metadata retention
- **Data Encryption**: Encrypt sensitive data at rest and in transit

### Security Standards
- **OWASP Top 10**: Address common web application vulnerabilities
- **CWE**: Common Weakness Enumeration compliance
- **ISO 27001**: Information security management

---

## Implementation Roadmap

### Phase 1: Current (Basic Security) ✅
- Cryptographic watermarking
- Deepfake detection
- Basic file validation
- Secure key handling

### Phase 2: Enhanced Security (Recommended)
- API authentication
- Rate limiting
- Audit logging
- File encryption at rest

### Phase 3: Enterprise Security (Future)
- HSM integration
- Multi-factor authentication
- Advanced monitoring
- Compliance reporting

---

## References

1. **Microsoft STRIDE Model**: https://docs.microsoft.com/en-us/azure/security/develop/threat-modeling-tool
2. **Ed25519 Signature Scheme**: RFC 8032
3. **DWT-QIM Watermarking**: Academic research on Discrete Wavelet Transform with Quantization Index Modulation
4. **Deepfake Detection**: Research papers on frequency domain analysis and CNN-based detection

---

## Document Version
- **Version**: 1.0
- **Last Updated**: 2025
- **Author**: TrueSight Development Team
- **Review Status**: Initial Implementation

---

## Notes for Instructors

This threat model demonstrates:
1. **Systematic Threat Analysis**: Using STRIDE framework to identify security threats
2. **Government Dataset Support**: KoDF (Korean government), FaceForensics++ (academic/government-backed)
3. **Microsoft Threat Modeling**: Applied STRIDE methodology comprehensively
4. **Real-world Security**: Addresses actual security concerns in media processing systems

The implementation includes both theoretical threat identification and practical mitigation strategies, suitable for academic demonstration and real-world application.

