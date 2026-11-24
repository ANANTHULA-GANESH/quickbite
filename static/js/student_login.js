/* Student login and registration forms. Account data is stored by the backend. */
(function () {
  "use strict";

  function showFieldError(form, field, message) {
    const error = form.querySelector(`[data-error-for="${field}"]`);
    if (error) error.textContent = message || "";
  }

  function clearErrors(form, messageBox) {
    form.querySelectorAll("[data-error-for]").forEach((el) => { el.textContent = ""; });
    messageBox.hidden = true;
    messageBox.textContent = "";
  }

  function validateName(form) {
    const name = form.elements.name.value.trim();
    if (!/^[A-Za-z][A-Za-z .'-]{1,59}$/.test(name)) {
      showFieldError(form, "name", "Enter your name using 2 to 60 letters.");
      return false;
    }
    return true;
  }

  function validatePhone(form) {
    if (!/^\d{10}$/.test(form.elements.phone.value)) {
      showFieldError(form, "phone", "Enter exactly 10 digits.");
      return false;
    }
    return true;
  }

  function showFormError(box, message) {
    box.textContent = message;
    box.hidden = false;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const login = document.getElementById("student-login-form");
    const register = document.getElementById("student-register-form");
    if (!login || !register) return;

    const loginError = document.getElementById("login-error");
    const registerError = document.getElementById("register-error");

    login.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearErrors(login, loginError);
      const validName = validateName(login);
      const validPhone = validatePhone(login);
      if (!validName || !validPhone) return;
      try {
        await QB.fetchJSON("/api/student/login", {
          method: "POST",
          body: JSON.stringify({
            name: login.elements.name.value.trim(),
            phone: login.elements.phone.value,
          }),
        });
        window.location.href = "/";
      } catch (err) {
        showFormError(loginError, err.message);
      }
    });

    register.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearErrors(register, registerError);
      const validName = validateName(register);
      const validPhone = validatePhone(register);
      const studentId = register.elements.student_id.value;
      const validId = /^\d{10}$/.test(studentId);
      if (!validId) showFieldError(register, "student_id", "Enter exactly 10 digits.");
      if (!validName || !validPhone || !validId) return;
      try {
        await QB.fetchJSON("/api/student/register", {
          method: "POST",
          body: JSON.stringify({
            name: register.elements.name.value.trim(),
            phone: register.elements.phone.value,
            student_id: studentId,
          }),
        });
        window.location.href = "/";
      } catch (err) {
        if (err.field) {
          showFieldError(register, err.field, err.message);
        } else {
          showFormError(registerError, err.message);
        }
      }
    });

    [login, register].forEach((form) => {
      form.addEventListener("input", (event) => {
        const field = event.target.name;
        if (field) showFieldError(form, field, "");
      });
    });
  });
})();
