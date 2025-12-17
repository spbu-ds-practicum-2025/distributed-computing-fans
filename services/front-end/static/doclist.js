
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
      let currentlySelected = "#";

      
      const openDoc = () => {
        window.location.href = `/users/${logged}/documents/${currentlySelected}`;
      }

      
      const deleteDoc = () => {
        const docId = currentlySelected;
        data = {
          id: docId
        }
        asyncDeleteDoc(data);
        // sending request to the server to DELETE
      }

      
      const shareDoc = () => {
        const shareTo = prompt("Укажите (через запятую и пробел) логины тех, с кем хотите поделиться доступом, например: user1, user2", "").trim().split(", ");
        if (shareTo.length === 0) return;
        const docId = currentlySelected;
        data = {
          id: docId,
          share_to: shareTo
        }
        asyncShareDoc(data);
        // sending request to the server to CHANGE THE OWNERSHIP (aka append new users' names to the array of owners)
      }

      
      const createDoc = () => {
        const docName = prompt("Укажите название нового файла", "Новый документ");
        const docId = Math.max(myDocs.map((elem) => elem.id)) + 1;  // id = max_id + 1
        data = {
          id: docId,
          title: docName
        }
        asyncCreateDoc(data);
        // sending request to the server to CREATE
      }

      
      document.getElementById("open").onclick = openDoc;
      document.getElementById("delete").onclick = deleteDoc;
      document.getElementById("share").onclick = shareDoc;
      document.getElementById("create").onclick = createDoc;
      
      
      for (const doc of myDocs) {
        let docDiv = document.createElement("div");
        docDiv.classList.add("doc-div");

        docDiv.onclick = () => {
          if (currentlySelected != doc.id) {
            document.getElementById("panel-buttons").classList.add("panel-buttons-visible");
            document.querySelectorAll(".doc-div").forEach((d) => {
              if (d.id != currentlySelected) {
                d.classList.remove("doc-selected");
              }
            })
          } else {
             document.getElementById("panel-buttons").classList.remove("panel-buttons-visible");
          }
          currentlySelected = doc.id;
          docDiv.classList.toggle("doc-selected");
        }
     
        
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





  const pathParts = window.location.pathname.split('/');
  const currentUser = pathParts[2];
  const docId = pathParts[4];

  const GATEWAY_BASE = "";
  const GATEWAY_WS = window.API_GATEWAY_WS || "ws://localhost:8000";

  let currentTitle = "";

  
  async function asyncCreateDoc(data) {
      try {
          const body = {
            title: data.title,
            content: ""
          }
          const resp = await fetch(`${GATEWAY_BASE}/documents/${data.id}`, {
              method: "PUT",
              headers: {
                  "Content-Type": "application/json"
              },
              body: JSON.stringify(body)
          });
          if (!resp.ok) {
              throw new Error("Не удалось создать документ");
          }
      } catch (err) {
          alert(err.message);
          console.error(err);
      }
  }



  async function asyncDeleteDoc(data) {
      try {
          const body = {
            title: data.title,
            content: ""
          }
          const resp = await fetch(`${GATEWAY_BASE}/documents/${data.id}`, {
              method: "PUT",
              headers: {
                  "Content-Type": "application/json"
              },
              body: JSON.stringify(body)
          });
          if (!resp.ok) {
              throw new Error("Не удалось удалить документ");
          }
      } catch (err) {
          alert(err.message);
          console.error(err);
      }
  }


  async function asyncShareDoc(data) {
      try {
          const body = {
            to: data.share_to
          }
          const resp = await fetch(`${GATEWAY_BASE}/documents/${data.id}`, {
              method: "PUT",
              headers: {
                  "Content-Type": "application/json"
              },
              body: JSON.stringify(body)
          });
          if (!resp.ok) {
              throw new Error("Не удалось поделиться доступом");
          }
      } catch (err) {
          alert(err.message);
          console.error(err);
      }
  }
}