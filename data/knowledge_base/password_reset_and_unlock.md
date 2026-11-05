# Password Reset and Account Unlock Procedure

| Field | Value |
|---|---|
| Document ID | KB-IAM-0011 |
| Owner | Identity and Access Management, IT Infrastructure |
| Version | 2.4 |
| Last reviewed | 2026-08-20 |
| Next review due | 2027-02-20 |
| Classification | Internal. Do not distribute outside Meridian Logistics. |
| Applies to | All employees and contractors with a Meridian Logistics corporate account |

> Note: This is a synthetic document created for development and testing. "Meridian Logistics" is a fictional company.

## 1. Purpose and Scope

This document explains how employees reset a forgotten or expired password and how locked accounts are unlocked. It also describes how the IT Service Desk handles these requests. The same corporate account is used for Windows sign-in, email, Microsoft 365, the remote access VPN, and most internal applications, so a password or lockout problem often shows up as several failures at once.

## 2. Password Policy Summary

- **Minimum length:** 14 characters.
- **Complexity:** Must not contain your username, your name, or the word "Meridian." Passphrases of four or more unrelated words are recommended.
- **Expiry:** Passwords expire every 180 days. You receive email reminders 14, 7, and 1 day before expiry.
- **History:** You cannot reuse any of your last 12 passwords.
- **Lockout:** An account is locked for 30 minutes after 5 consecutive failed sign-in attempts. The lock clears automatically, or IT can unlock it sooner.
- **Sharing:** Never share your password with anyone, including IT staff, managers, and assistants. The Service Desk will never ask for your password or MFA approval.

## 3. Resetting a Forgotten Password Yourself (Self-Service)

You can reset your own password at `https://account.meridian.example/reset` if you have registered for multifactor authentication (MFA). Self-service reset is the fastest option and is available 24/7.

1. Open the reset page from any device with internet access, including a personal phone.
2. Enter your corporate email address.
3. Approve the MFA push in the Authenticator app, or enter the one-time code shown in the app.
4. Choose a new password that meets the policy in Section 2.
5. Wait about two minutes for the change to sync, then sign in with the new password.

If you have not registered MFA, or you no longer have access to your registered phone, you cannot use self-service reset. Contact the Service Desk (Section 6). See KB-IAM-0015 for MFA registration.

## 4. Changing a Password Before It Expires

If you know your current password, you can change it at any time:

- **On a managed Windows laptop:** Press Ctrl+Alt+Delete and select "Change a password."
- **On a managed Mac:** Open System Settings, then Users & Groups, then select "Change" next to your password.
- **From any browser:** Visit `https://account.meridian.example/change`.

After changing your password, update it on every other device that stores it, such as your phone's email app. A stored old password is the most common cause of repeated lockouts shortly after a change.

## 5. Unlocking a Locked Account

### 5.1 Wait for Automatic Unlock

A locked account unlocks automatically after 30 minutes. During this time, stop trying to sign in. Repeated attempts restart the lockout timer.

### 5.2 Find and Remove the Cause

Frequent lockouts usually come from an old password saved somewhere. Check these before the account locks again:

- Your phone's email, calendar, or Wi-Fi settings.
- Any second laptop, tablet, or personal device where you signed in with your work account.
- Saved credentials in remote desktop or mapped network drives. On Windows, open Credential Manager and remove old entries for Meridian systems.
- Scheduled tasks or scripts running under your account.

### 5.3 Request an Immediate Unlock

If you cannot wait 30 minutes, contact the Service Desk. The analyst verifies your identity and unlocks the account. Unlock requests are not subject to the P3 response target when the user is unable to work. They are treated as P2 if a deadline or customer-facing activity is affected.

## 6. Contacting the Service Desk for a Reset or Unlock

| Channel | Details | Availability |
|---|---|---|
| Self-service portal | `https://help.meridian.example` | 24/7 |
| Phone | +1-555-0142 (Americas), +44-20-5550-0142 (EMEA), +65-5550-0142 (APAC) | 24/5 (Monday to Friday) |
| Chat | Service Desk channel in Microsoft Teams | 07:00 to 19:00 local time, weekdays |

You will be asked to verify your identity before any reset or unlock. Expect questions such as your employee ID, your manager's name, and a callback to the mobile number on file. The analyst will never ask for your current password or an MFA code. If someone asks for these, end the call and report it to security@meridian.example.

## 7. Service Desk Procedure (L1 Analysts)

### 7.1 Identity Verification

1. Follow the caller verification procedure in KB-SD-0003 before any account change.
2. Call back on the mobile number stored in the HR system. Do not use a number supplied by the caller.
3. If the caller cannot be verified, do not reset the password. Ask the caller's manager to confirm identity through the manager verification workflow.

### 7.2 Resetting a Password

1. Open the user in the identity management console and select "Reset password."
2. Generate a temporary password and deliver it by the approved method (SMS to the verified number, or to the manager for high-risk accounts). Never send it by email or chat.
3. Set the account to require a password change at next sign-in.
4. Record the verification method and time in the ticket.

### 7.3 Unlocking an Account

1. Check the sign-in log for the source of the failed attempts.
2. If the failures come from an unknown IP address or country, do not simply unlock. Escalate to the Security Operations Center (SOC) as a possible attack.
3. If the failures come from the user's own device, unlock the account and ask the user to remove the stale credential (Section 5.2).

### 7.4 Escalation

- Escalate to the **SOC** for suspected password spraying, repeated lockouts from unfamiliar locations, or any report that credentials were shared or phished.
- Escalate to **IAM Engineering** for accounts that cannot be unlocked, synchronization failures between the directory and Microsoft 365, or reset pages returning errors.

## 8. Common Problems After a Reset

| Symptom | Likely cause | What to do |
|---|---|---|
| New password rejected | Does not meet policy, or was used within the last 12 passwords | Choose a longer, different passphrase. |
| New password works on the web but not on the laptop | Laptop is offline or not yet synced | Connect to the VPN or office network, lock and unlock the device, then sign in with the new password. |
| Phone email keeps asking for a password | Old password saved on the phone | Remove and re-add the account with the new password. |
| Account locks again within minutes | Old password stored on another device or in Credential Manager | Follow Section 5.2. |
| "Your password has expired" at the VPN | Password expired | Reset at `https://account.meridian.example/reset`, then reconnect. |

## 9. Frequently Asked Questions

**Can the Service Desk tell me my current password?** No. Passwords are stored in a form that nobody, including IT, can read. Only a reset is possible.

**Why do I need MFA to reset my password?** MFA proves that the person resetting the password is you and not someone who only knows your email address.

**I reset my password but the VPN still says "Login failed."** Wait about two minutes for synchronization. If it still fails, confirm you can sign in to `https://portal.office.com` with the new password, then see KB-NET-0042.

**Do contractors follow the same password policy?** Yes. The same policy applies to all corporate accounts.

**I think someone else knows my password.** Change it immediately, then notify the Service Desk and security@meridian.example.

## 10. Related Documents

| ID | Title |
|---|---|
| KB-IAM-0015 | Multifactor Authentication Enrollment and Recovery |
| KB-NET-0042 | Remote Access VPN: Troubleshooting and Support Procedure |
| KB-SD-0003 | Caller Identity Verification Procedure |
| POL-SEC-001 | Information Security Policy |

## 11. Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 2.4 | 2026-08-20 | Identity and Access Management | Added stale-credential checklist and SOC escalation criteria |
| 2.3 | 2026-02-11 | Identity and Access Management | Extended password expiry from 90 to 180 days |
| 2.2 | 2025-07-30 | IT Infrastructure | Moved self-service reset to the new account portal |
