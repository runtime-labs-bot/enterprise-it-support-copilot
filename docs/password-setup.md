Employees choose their first password in the Copilot website.

1. Sign in as an admin, open **Admin dashboard → Employees**, and create or select an employee.
2. Expand **Set up login account**, select the company-approved account role, and click **Generate password setup link**.
3. Share the link privately with that employee. The employee opens it, enters and confirms their password, and can select **Show password**.
4. After setup, the employee signs in with their work email and chosen password.

Links expire after 24 hours and work once. Issuing a replacement invalidates previous links. The backend stores a hash of the link token. Setup creates a login linked to the existing employee; it cannot overwrite an existing login or let the recipient choose their role. Passwords are hashed with Argon2id. No email delivery is configured: an admin shares the generated link manually.

Set `COPILOT_PUBLIC_URL` in the Copilot environment to the Streamlit URL employees can reach. The development default is `http://localhost:8501`; use your HTTPS address when deployed. Restart Streamlit after changing configuration.

The backend requires migration `0007_password_invitations` (`python -m alembic upgrade head`). Restart the backend and Copilot API after updating their code. Existing CLI password tools remain available for trusted administrator recovery, but employees do not need them.
