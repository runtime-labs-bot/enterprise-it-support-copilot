# Multifactor Authentication (MFA) Enrollment and Recovery

| Field | Value |
|---|---|
| Document ID | KB-IAM-0015 |
| Owner | Identity and Access Management, IT Infrastructure |
| Version | 1.8 |
| Last reviewed | 2026-09-02 |
| Next review due | 2027-03-02 |
| Classification | Internal. Do not distribute outside Meridian Logistics. |
| Applies to | All employees and contractors with a Meridian Logistics corporate account |

> Note: This is a synthetic document created for development and testing. "Meridian Logistics" is a fictional company.

## 1. Purpose and Scope

Multifactor authentication (MFA) requires a second proof of identity in addition to your password. At Meridian Logistics, MFA is mandatory for email, Microsoft 365, the remote access VPN, the self-service password reset page, and all internal applications. This document explains how to enroll in MFA, how to move MFA to a new phone, and what to do if your phone is lost, stolen, or unavailable.

## 2. Supported MFA Methods

| Method | Status | Notes |
|---|---|---|
| Authenticator app push (with number matching) | Recommended | You approve a sign-in by entering the number shown on screen. |
| Authenticator app one-time code | Supported | Six-digit code that changes every 30 seconds. Useful with poor signal. |
| FIDO2 security key | Supported on request | Issued by the Service Desk for staff who cannot use a personal phone, and for privileged accounts. |
| SMS text message | Not supported | Disabled in 2025 because of SIM-swap risk. |
| Voice call | Not supported | Disabled in 2025. |

You should register at least two methods, for example the Authenticator app and a FIDO2 key, so one failure does not lock you out.

## 3. Enrolling in MFA for the First Time

New employees must complete enrollment within 7 days of their start date. You need your laptop and your phone.

1. On your laptop, sign in at `https://account.meridian.example/security` using your corporate email and temporary password.
2. When prompted, select "Set up Authenticator app."
3. On your phone, install **Microsoft Authenticator** from the App Store or Google Play. Use only the official app.
4. In the app, choose "Add account," then "Work or school account," then "Scan QR code."
5. Scan the QR code displayed on your laptop.
6. Approve the test notification by entering the number shown on the laptop.
7. Add a second method under "Security info," such as a one-time code backup or a FIDO2 key.

Company policy allows the Authenticator app on a personal phone. The app does not give Meridian Logistics access to your personal data or photos.

## 4. Moving MFA to a New Phone

Do this before you retire the old phone.

**If you still have your old phone:**

1. On the old phone, open Authenticator and confirm cloud backup is on (Settings, then Backup).
2. On the new phone, install Authenticator and choose "Restore from backup." Sign in with your personal backup account.
3. Test by signing in to `https://portal.office.com` and approving the prompt on the new phone.
4. Remove the old phone from your security info at `https://account.meridian.example/security`.

**If you no longer have your old phone:** Follow Section 5.

## 5. Lost, Stolen, or Unavailable Phone

### 5.1 If the Phone Is Lost or Stolen

Report it immediately to the Service Desk and security@meridian.example, even outside business hours. The SOC will:

1. Revoke all active sign-in sessions for your account.
2. Remove the lost phone from your security info.
3. Review recent sign-in activity for suspicious behavior.

You should also change your password once the account has been secured.

### 5.2 Getting Back In

You cannot self-recover MFA without a registered method. Contact the Service Desk. After identity verification (KB-SD-0003), the analyst issues a **Temporary Access Pass (TAP)**:

- A single-use code valid for 8 hours.
- Used at `https://account.meridian.example/security` to register your new phone.
- Delivered by the approved method (SMS to your verified mobile number, or to your manager for high-risk accounts). Never sent by email or chat.

Use the TAP promptly. After it expires, a new one must be requested.

### 5.3 While Traveling

If you lose access to MFA while abroad, contact the Service Desk by phone. Time zone coverage is listed in Section 8. Identity verification may take longer if you cannot be reached on your usual mobile number, and your manager may be asked to confirm your identity.

## 6. Common MFA Problems

| Symptom | Likely cause | What to do |
|---|---|---|
| No push notification arrives | Phone offline, notifications disabled, or battery saver blocking the app | Check connectivity, enable notifications for Authenticator, then open the app manually to look for a pending request. |
| "MFA request timed out" | Push not approved within 60 seconds | Retry and approve promptly. |
| Number matching code does not work | Wrong number entered or old prompt approved | Cancel and start a new sign-in. Never approve a prompt you did not start. |
| One-time code rejected | Phone clock is off by more than a minute | Set the phone's date and time to automatic. |
| Approved prompt but sign-in still fails | Cached sign-in or old session | Close the browser, reopen, and retry. |
| Received an MFA prompt you did not request | Someone may know your password | Deny it. Contact the Service Desk and security@meridian.example immediately, then change your password. |

## 7. Security Notes

- **Never approve a prompt you did not trigger.** Attackers who obtain a password send repeated prompts hoping the user approves one out of habit. This is known as MFA fatigue.
- **Never read out or send a one-time code to anyone.** No Meridian employee or IT analyst will ask for it.
- **Do not register MFA on a device you do not control.** Use only your own phone or an IT-issued key.
- The SOC monitors for unusual MFA activity. Repeated denied prompts or sign-ins from unfamiliar countries may lead to a temporary account lock for your protection.

## 8. Contacting the Service Desk

| Channel | Details | Availability |
|---|---|---|
| Self-service portal | `https://help.meridian.example` | 24/7 |
| Phone | +1-555-0142 (Americas), +44-20-5550-0142 (EMEA), +65-5550-0142 (APAC) | 24/5 (Monday to Friday) |
| Chat | Service Desk channel in Microsoft Teams | 07:00 to 19:00 local time, weekdays |

A lost phone is treated as a security incident and handled as P2, regardless of the usual response targets.

## 9. Service Desk Procedure (L1 Analysts)

1. Verify the caller using KB-SD-0003. Do not proceed if verification fails.
2. If the phone is lost or stolen, open a security incident, notify the SOC, and confirm session revocation before issuing a TAP.
3. Issue a Temporary Access Pass valid for 8 hours, single use. Record the delivery method in the ticket.
4. Confirm the user has registered the new method and removed the old one before closing the ticket.
5. For FIDO2 key requests, confirm manager approval, order from stock, and record the key serial number against the user.
6. Escalate to **IAM Engineering** if TAP issuance fails or the registration page returns errors.

## 10. Frequently Asked Questions

**Do I have to install the Authenticator app on my personal phone?** You can use a personal phone or request an IT-issued FIDO2 security key. Staff who cannot use a personal phone should contact the Service Desk.

**Why was SMS removed as an option?** Text messages can be intercepted or redirected through SIM-swap attacks. App-based methods and security keys are significantly safer.

**How many methods should I register?** At least two, so that losing one device does not lock you out.

**Can I use the same Authenticator app for my personal accounts?** Yes. The app can hold both personal and work accounts, and they remain separate.

**How long does a Temporary Access Pass last?** Eight hours, and it can be used only once.

## 11. Related Documents

| ID | Title |
|---|---|
| KB-IAM-0011 | Password Reset and Account Unlock |
| KB-NET-0042 | Remote Access VPN: Troubleshooting and Support Procedure |
| KB-SD-0003 | Caller Identity Verification Procedure |
| POL-SEC-001 | Information Security Policy |

## 12. Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.8 | 2026-09-02 | Identity and Access Management | Added number matching, FIDO2 key option, and TAP lifetime of 8 hours |
| 1.7 | 2025-11-14 | Identity and Access Management | Disabled SMS and voice call methods |
| 1.6 | 2025-04-09 | IT Infrastructure | Added lost phone procedure and SOC notification |
