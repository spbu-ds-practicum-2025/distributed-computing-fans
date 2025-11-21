
const logged = localStorage.getItem("logged");
if (!logged) {
  window.location.href = "/";
} else {
  document.getElementById("btn-username").innerHTML = `Выйти (${logged})`;
  
  fetch(`/api/userdocs/${logged}`)
    .then(response => {
      if (!response.ok) {
        throw new Error("User not found");
      }
      return response.json();
    })
    .then(db => {
      let myDocs = db.my_docs || [];
      let sharedDocs = db.shared_docs || [];

      for (const doc of myDocs) {
        let docDiv = document.createElement("div");
        docDiv.classList.add("doc-div");
        docDiv.ondblclick = () => {
          window.location.href = `/users/${logged}/documents/${doc.id}`;
        };

        let docTitle = document.createElement("p");
        docTitle.classList.add("doc-p");
        docTitle.innerHTML = doc.title;

        let innerDocDiv = document.createElement("div");
        innerDocDiv.classList.add("inner-doc-div");
        innerDocDiv.innerHTML = doc.shared_to.length > 0 ? "</p>есть общий доступ</p>" : "";

        docDiv.appendChild(innerDocDiv);
        docDiv.appendChild(docTitle);
        document.getElementById("my-docs").appendChild(docDiv);
      }

      for (const doc of sharedDocs) {
        let docDiv = document.createElement("div");
        docDiv.classList.add("sh-doc-div");
        docDiv.ondblclick = () => {
          window.location.href = `/users/${logged}/documents/${doc.id}`;
        };

        let docTitle = document.createElement("p");
        docTitle.classList.add("sh-doc-p");
        docTitle.innerHTML = doc.title;

        let innerDocDiv = document.createElement("div");
        innerDocDiv.classList.add("sh-inner-doc-div");
        innerDocDiv.innerHTML = `</p>автор <strong>${doc.shared_from}</strong></p>`;

        docDiv.appendChild(innerDocDiv);
        docDiv.appendChild(docTitle);
        document.getElementById("shared-docs").appendChild(docDiv);
      }
    })
    .catch(err => {
      console.error(err);
      alert("Ошибка загрузки документов.");
    });

  document.getElementById("btn-username").addEventListener("click", () => {
    localStorage.removeItem("logged");
    window.location.href = "/";
  });
}



