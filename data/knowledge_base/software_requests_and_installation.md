# Software Requests and Installation Procedure

| Field | Value |
|---|---|
| Document ID | KB-SW-0008 |
| Owner | End User Computing, IT Infrastructure |
| Version | 2.1 |
| Last reviewed | 2026-09-28 |
| Next review due | 2027-03-28 |
| Classification | Internal. Do not distribute outside Meridian Logistics. |
| Applies to | All employees and contractors with a corporate-managed Windows or macOS device |

> Note: This is a synthetic document created for development and testing. "Meridian Logistics" is a fictional company.

## 1. Purpose and Scope

This document explains how to install approved software, how to request software that is not in the catalog, and how requests are reviewed. It applies to corporate-managed laptops. It does not cover software for servers or cloud environments, which follow the Engineering Change Management process (KB-ENG-0019).

## 2. Standard User Rights

Employees do not have local administrator rights on their laptops. This protects the device and the company network from malware and unapproved changes. Software is installed through approved channels instead:

- **Company Portal (Windows and macOS):** a self-service catalog of pre-approved applications.
- **IT-deployed software:** applications pushed automatically to your device based on your role, such as accounting tools for Finance.
- **Request workflow:** a ticket-based process for anything not in the catalog.

## 3. Installing Approved Software from the Company Portal

1. Open **Company Portal** from the Start menu (Windows) or Applications folder (macOS).
2. Sign in with your corporate account if prompted.
3. Browse or search for the application. Only approved software appears.
4. Select the application and choose **Install**.
5. Wait for the status to change to "Installed." Large applications can take up to 30 minutes.
6. Restart the application, or the laptop if prompted.

If an application appears in the portal but fails to install, check that you are connected to the VPN or office network and that your laptop has at least 10 GB of free disk space. If it still fails, open a ticket with the application name and the error message.

## 4. Pre-Approved Software Catalog (Summary)

| Category | Examples |
|---|---|
| Productivity | Microsoft 365 apps, Adobe Acrobat Reader, 7-Zip |
| Collaboration | Microsoft Teams, Zoom (client only) |
| Browsers | Microsoft Edge, Google Chrome |
| Development | Visual Studio Code, Git, Python 3.12, Node.js LTS (engineering roles only) |
| Design | Figma desktop client, Adobe Creative Cloud (licensed, requires approval) |
| Utilities | Notepad++, Greenshot, PuTTY |

This list is a summary. The Company Portal always reflects the current catalog.

## 5. Requesting Software That Is Not in the Catalog

### 5.1 Before You Submit

Check whether an approved application already meets your need. Many requests can be solved with software that is already available. Consider whether the software is free, subscription-based, or licensed per user, because cost approval differs.

### 5.2 How to Submit

1. Open the self-service portal at `https://help.meridian.example`.
2. Choose "Request software" and fill in the form.
3. Include the software name, vendor, version, business justification, how many people need it, and whether it is free or paid.
4. Provide the vendor website or download link.
5. Select your manager as approver.

### 5.3 Approval Steps

| Step | Reviewer | What they check | Typical time |
|---|---|---|---|
| 1 | Line manager | Business need | 1 business day |
| 2 | Cost center owner (paid software only) | Budget and license cost | 2 business days |
| 3 | IT Security | Vendor reputation, data handling, vulnerabilities | 3 to 5 business days |
| 4 | End User Computing | Compatibility and packaging for deployment | 2 to 5 business days |

Software that handles customer data, connects to external cloud services, or requires elevated permissions is subject to a more detailed security review, which can take up to 15 business days.

### 5.4 Possible Outcomes

- **Approved:** The software is deployed to your device through the Company Portal, and you receive a ticket update.
- **Approved with conditions:** For example, use limited to a specific role or version.
- **Rejected:** The ticket explains the reason and, where possible, suggests an approved alternative.

## 6. Software That Is Not Permitted

The following are not allowed on corporate devices and will be removed automatically if detected:

- Personal VPN clients, proxy tools, and tunnel software (they bypass corporate access controls).
- Peer-to-peer file sharing applications and torrent clients.
- Remote access tools not issued by IT, such as unapproved screen-sharing or remote desktop tools.
- Cracked, pirated, or unlicensed software.
- Cryptocurrency mining software.
- Browser extensions that read all page data and are not on the approved extension list.

Installing prohibited software may result in a security incident review and disciplinary action under POL-SEC-007.

## 7. Temporary Administrative Access

Some roles need local administrator access for a specific task, such as installing a driver for lab equipment.

1. Open a ticket explaining the task, the software involved, and the time needed.
2. Obtain manager approval.
3. IT Security grants just-in-time elevation, valid for a maximum of 60 minutes on one device.
4. All actions during elevation are logged.

Permanent administrator rights are not granted to standard users. Developers needing frequent elevation should use the approved developer workstation configuration instead.

## 8. Updates and Patching

- Operating system and application updates are deployed automatically and may require a restart. Restart within 3 days of a prompt.
- Devices more than 30 days behind on security patches may be denied VPN access with a "Posture assessment failed" message (see KB-NET-0042).
- Do not postpone updates repeatedly. After the deadline, the device restarts automatically outside business hours.

## 9. Common Problems

| Symptom | Likely cause | What to do |
|---|---|---|
| Application missing from the Company Portal | Not in the catalog or not available for your role | Submit a software request (Section 5). |
| Install stuck at "Waiting" | Device not connected to the network or another install in progress | Connect to the VPN or office network, wait 10 minutes, then retry. |
| "Administrator permission required" prompt | Installer not delivered through the Company Portal | Do not try to bypass it. Use the portal or open a ticket. |
| Application installed but cannot sign in | License not yet assigned | Allow up to 24 hours, then open a ticket. |
| Application removed overnight | Detected as non-compliant or prohibited | Check the notification email from IT Security and open a ticket if you believe it was removed in error. |

## 10. Service Desk Procedure (L1 Analysts)

1. Check whether the requested software is already in the Company Portal. If so, guide the user through installation and close the ticket.
2. If not in the catalog, confirm a software request form is filled in completely and route it to the approval workflow. Do not promise a date.
3. Never install software manually on behalf of a user outside the approved process, and never share local administrator credentials.
4. For failed installs, collect the application name, error message, device asset tag, free disk space, and network status. Escalate to **End User Computing L2** if the cause is not resolved.
5. Escalate to the **SOC** if you find prohibited software or a user reports installing something from a suspicious link.

## 11. Frequently Asked Questions

**Can I install a free tool I found online if it is only for me?** No. All software on a corporate device must come from the catalog or be approved through the request process, even if it is free.

**Can I get administrator rights on my laptop?** Not permanently. Request temporary elevation for a specific task (Section 7).

**How long will my request take?** Most paid or non-standard requests take 5 to 10 business days. Security reviews of complex software can take up to 15.

**Can I use a personal license I already own?** Not on a corporate device without approval. Personal licenses may breach vendor terms and cannot be managed or audited by IT.

**Why was my software removed?** Software that is prohibited, unlicensed, or flagged by IT Security is removed automatically. Check your email for details.

## 12. Related Documents

| ID | Title |
|---|---|
| KB-NET-0042 | Remote Access VPN: Troubleshooting and Support Procedure |
| KB-ENG-0019 | Engineering Change Management |
| POL-SEC-001 | Information Security Policy |
| POL-SEC-007 | Acceptable Use Policy |

## 13. Revision History

| Version | Date | Author | Summary |
|---|---|---|---|
| 2.1 | 2026-09-28 | End User Computing | Added just-in-time elevation limit and detailed security review timeline |
| 2.0 | 2026-04-17 | End User Computing | Moved to the Company Portal catalog and removed local admin exceptions |
| 1.9 | 2025-09-05 | IT Infrastructure | Added prohibited software list |
