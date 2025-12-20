
document.getElementById("handle-login").addEventListener("click", () => {
  const username = document.getElementById("inp-user-id").value.trim();
  if (username) {
    sessionStorage.setItem("logged", username);
  localStorage.logged = username;
    window.location.href = `/users/${encodeURIComponent(username)}/documents`;
  } else {
    alert("Пожалуйста, введите свой ID пользователя");
  }
});
