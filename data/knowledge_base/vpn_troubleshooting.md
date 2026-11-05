# Remote Access VPN: Troubleshooting and Support Procedure

| Field | Value |
|---|---|
| Document ID | KB-NET-0042 |
| Owner | Network Operations, IT Infrastructure |
| Version | 3.2 |
| Last reviewed | 2026-09-15 |
| Next review due | 2027-03-15 |
| Classification | Internal. Do not distribute outside Meridian Logistics. |
| Applies to | All employees and contractors with a corporate-managed Windows or macOS device |

> Note: This is a synthetic document created for development and testing. "Meridian Logistics" is a fictional company.

## 1. Purpose and Scope

This document describes how employees troubleshoot problems connecting to the Meridian Logistics remote access VPN, and how the IT Service Desk handles VPN incidents. It covers the corporate VPN client (Cisco Secure Client) on managed laptops. It does not cover VPN access from personal devices, which is not permitted under the Acceptable Use Policy (POL-SEC-007).

## 2. VPN Environment Overview

- **VPN client:** Cisco Secure Client 5.1 (installed and updated automatically through the Company Portal).
- **Gateways:** `vpn-emea.meridian.example`, `vpn-amer.meridian.example`, `vpn-apac.meridian.example`. The client selects the nearest gateway automatically. Users should not enter a gateway address manually unless instructed by IT.
- **Authentication:** Corporate username (the email prefix, for example `jdoe`), network password, and a multifactor authentication (MFA) push approval through the Authenticator app.
- **Connection mode:** Split tunnel. Traffic to internal systems goes through the VPN. General internet traffic does not.
- **Session limits:** Sessions disconnect after 12 hours or after 30 minutes of inactivity. Users must reconnect and re-approve MFA.
- **Ports used:** TCP and UDP 443 outbound. No inbound ports are required.

## 3. Before You Begin

Have the following ready before you troubleshoot or contact IT:

1. Your laptop's asset tag (printed on the bottom of the device).
2. The exact text of any error message shown by the VPN client.
3. The network you are on (home Wi-Fi, mobile hotspot, hotel, or office).
4. The time the problem started.

Never share your password or MFA approval codes with anyone, including IT staff. The Service Desk will never ask for them.

## 4. First-Line Troubleshooting Steps for Employees

Work through these steps in order. Most VPN issues are resolved by step 5.

### 4.1 Confirm Internet Access

Open a browser and load a public site such as the company's external website. If it does not load, the problem is your local network, not the VPN. Restart your router, move closer to the Wi-Fi access point, or switch to a mobile hotspot to test.

### 4.2 Check for Captive Portals

Hotel, airport, and café Wi-Fi networks often require you to accept terms in a browser before internet access is granted. Open a browser, visit `http://neverssl.com`, and complete any sign-in page that appears. Then retry the VPN.

### 4.3 Confirm Your Account Is Active

Sign in to the Microsoft 365 web portal at `https://portal.office.com`. If sign-in fails, your account may be locked or your password may have expired. See KB-IAM-0011 (Password Reset and Account Unlock). VPN access depends on the same account.

### 4.4 Verify MFA

Make sure your phone has a network connection and that notifications are enabled for the Authenticator app. If the MFA push does not arrive, open the Authenticator app manually and check for a pending approval. If you have a new phone, you must re-register MFA through the self-service portal before the VPN will work.

### 4.5 Restart the VPN Client

Fully quit Cisco Secure Client (right-click the tray icon on Windows or menu bar icon on macOS, then choose Quit) and relaunch it. Then reconnect.

### 4.6 Restart the Laptop

Save your work and restart the device. A restart clears stuck network adapters and finishes pending updates that may block the VPN client.

### 4.7 Check the Date and Time

An incorrect system clock causes certificate and MFA failures. Make sure the date, time, and time zone are set to update automatically. On Windows: Settings, Time & language, Date & time, then enable "Set time automatically."

### 4.8 Try a Different Network

If you are on home Wi-Fi, try a mobile hotspot. Some home routers, ISPs, and public networks block or throttle VPN traffic. If the VPN works on a hotspot but not on your home network, include that detail when you contact IT.

## 5. Common Error Messages and Their Meaning

| Message shown in client | Likely cause | What to do |
|---|---|---|
| "Login failed" | Wrong password, expired password, or locked account | Verify sign-in at the Microsoft 365 portal. If it fails there, follow KB-IAM-0011. |
| "MFA request timed out" | Push notification not approved within 60 seconds | Retry and approve promptly. Check phone connectivity and Authenticator notifications. |
| "The VPN connection failed due to unsuccessful domain name resolution" | No internet access, DNS failure, or captive portal | Complete steps 4.1 and 4.2. Try a different network. |
| "Connection attempt has timed out" | Network blocks outbound port 443 to the gateway | Try a mobile hotspot. If that works, report the home network issue to IT. |
| "Certificate validation failure" | Incorrect system clock or missing device certificate | Complete step 4.7. If it persists, contact IT. The device certificate may need to be reissued. |
| "Posture assessment failed" | Device is missing required security updates or endpoint protection is not running | Install pending updates and restart. Do not disable or uninstall security software. Contact IT if the message continues. |
| "Session terminated by administrator" | Account flagged by security monitoring, or too many failed logins | Contact the Service Desk immediately. Do not retry repeatedly. |
| "Another VPN client is installed" | Conflicting third-party VPN software | Contact IT. Do not install personal VPN software on managed devices. |

## 6. Security Rules During Troubleshooting

- **Do not disable** Microsoft Defender, CrowdStrike Falcon, the Windows firewall, or any other security software, even temporarily. Disabling endpoint protection on a managed device violates the Information Security Policy (POL-SEC-001) and will cause VPN posture checks to fail.
- **Do not** edit VPN profile files, registry entries, or hosts files manually.
- **Do not** install VPN client software from the internet. Only install it through the Company Portal.
- **Do not** use browser-based or third-party "free VPN" services as a workaround. These bypass corporate access controls and are reported to Security Operations automatically.
- If you suspect your credentials were compromised, for example you approved an MFA prompt you did not initiate, contact the Service Desk and the Security Operations Center (SOC) immediately at security@meridian.example.

## 7. When to Contact the IT Service Desk

Contact the Service Desk if any of the following apply:

- You have completed all steps in Section 4 and the VPN still does not connect.
- You see "Posture assessment failed," "Certificate validation failure," or "Session terminated by administrator."
- Multiple colleagues in the same location report the same problem. This may indicate a gateway or regional outage.
- The VPN connects but you cannot reach specific internal applications.

### Contact Channels

| Channel | Details | Availability |
|---|---|---|
| Self-service portal | `https://help.meridian.example` | 24/7 |
| Phone | +1-555-0142 (Americas), +44-20-5550-0142 (EMEA), +65-5550-0142 (APAC) | 24/5 (Monday to Friday) |
| Chat | Service Desk channel in Microsoft Teams | 07:00 to 19:00 local time, weekdays |

If you cannot connect to the VPN, use your phone or a personal device to open a ticket through the self-service portal or phone.

### Information to Include in the Ticket

1. Your name and the asset tag of your laptop.
2. The exact error message, or a screenshot.
3. Operating system and version (for example, Windows 11 23H2).
4. Cisco Secure Client version (open the client and select the information icon).
5. The network you were using and whether other networks work.
6. The time the problem began and the steps you already tried.

## 8. Service Desk Procedure (L1 Analysts)

### 8.1 Triage

1. Verify the caller's identity using the standard verification procedure (KB-SD-0003). Never ask for passwords or MFA codes.
2. Check the Network Operations status page for active VPN incidents before troubleshooting individually.
3. Search open incidents for the same error from the same site or region. If three or more related tickets exist, link them to a major incident record and notify the on-call Network Engineer.

### 8.2 Account and Access Checks

1. Confirm the account is enabled and not locked in the identity directory.
2. Confirm the user is a member of the `VPN-Users` security group. If not, access requires manager approval through the access request workflow (KB-IAM-0027).
3. Review the VPN authentication log for the user over the last 24 hours. Note the failure reason code.

### 8.3 Device Checks

1. Confirm the device is enrolled in device management and shows as compliant.
2. Confirm the device certificate is valid and has not expired. Reissue it from the management console if needed.
3. Confirm endpoint protection is running and operating system patches are within 30 days.

### 8.4 Resolution and Escalation

- Resolve at L1 if the cause is a locked account, expired password, MFA re-registration, incorrect clock, or missing group membership.
- Escalate to **L2 Network Support** for client reinstallation failures, certificate issuance problems, and suspected network blocking.
- Escalate to **Network Operations (on-call)** for gateway outages, regional failures, or multiple users affected.
- Escalate to the **SOC** for suspected account compromise, repeated MFA prompts the user did not initiate, or "Session terminated by administrator" events.

### 8.5 Service Level Targets

| Priority | Example | Response | Resolution target |
|---|---|---|---|
| P1 | VPN unavailable for an entire region | 15 minutes | 4 hours |
| P2 | VPN unavailable for a team or site | 30 minutes | 8 hours |
| P3 | Single user cannot connect | 4 business hours | 2 business days |
| P4 | Slow performance, intermittent drops | 1 business day | 5 business days |

## 9. Frequently Asked Questions

**Can I use the VPN from my personal laptop or phone?**
No. Remote access is available only from corporate-managed devices. Personal devices can access Microsoft 365 web applications directly without VPN.

**Why does the VPN disconnect after 30 minutes?**
Sessions disconnect after 30 minutes of inactivity as a security control. Reconnect and approve MFA again.

**Can I connect from another country?**
Connections from approved countries work normally. Connections from restricted countries are blocked by default. Contact the Service Desk at least five business days before international travel to confirm access.

**The VPN is connected, but I cannot open an internal website. What should I do?**
Confirm you can reach another internal resource. If only one application fails, the problem is likely with that application and not the VPN. Open a ticket for the application owner and mention that you are connected to the VPN.

**My VPN is very slow. Is that expected?**
Performance depends on your home internet connection and the distance to the gateway. Close bandwidth-heavy applications, use a wired connection where possible, and report persistent slowness to the Service Desk with a speed test result.

**I got an MFA prompt I did not request. What should I do?**
Deny the request. Contact the Service Desk and the SOC immediately. Change your password after the account has been secured by IT.

## 10. Related Documents

| ID | Title |
|---|---|
| KB-IAM-0011 | Password Reset and Account Unlock |
| KB-IAM-0027 | Requesting VPN and Application Access |
| KB-SD-0003 | Caller Identity Verification Procedure |
| POL-SEC-001 | Information Security Policy |
| POL-SEC-007 | Acceptable Use Policy |

## 11. Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 3.2 | 2026-09-15 | Network Operations | Added posture assessment guidance and updated client to version 5.1 |
| 3.1 | 2026-03-02 | Network Operations | Updated gateway names and session limits |
| 3.0 | 2025-10-20 | IT Infrastructure | Rewrote document for the Cisco Secure Client migration |