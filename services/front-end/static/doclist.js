
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
      let currentlySelected = null;

      document.getElementById("panel-buttons").classList.add("panel-buttons-visible");
      
      const openDoc = () => {
        if (!currentlySelected) {
            alert("Выберите документ для открытия");
            return;
        }
        window.location.href = `/users/${logged}/documents/${currentlySelected}`;
      }

      const deleteDoc = () => {
          if (!currentlySelected) {
              alert("Выберите документ для удаления");
              return;
          }
          
          const selectedElement = document.querySelector(`[data-doc-id="${currentlySelected}"]`);
          
          if (selectedElement && selectedElement.classList.contains("sh-doc-div")) {
              alert("Вы не можете удалить документ, к которому имеете общий доступ");
              return;
          }

          if (!confirm("Вы уверены, что хотите удалить этот документ?")) {
              return;
          }
          
          const data = {
              id: currentlySelected
          };
          
          asyncDeleteDoc(data)
              // .then(() => {
              //     const docElement = document.querySelector(`[data-doc-id="${currentlySelected}"]`);
              //     if (docElement) {
              //         docElement.remove();
              //     }

              //     document.getElementById("panel-buttons").classList.remove("panel-buttons-visible");
              //     currentlySelected = null;
                  
              //     location.reload();
              // })
              // .catch(err => {
              //     console.error("Ошибка при удалении:", err);
              // });
      };

      
      const shareDoc = () => {
        if (!currentlySelected) {
            alert("Выберите документ, чтобы поделиться им");
            return;
        }

        const selectedElement = document.querySelector(`[data-doc-id="${currentlySelected}"]`);
        
        if (selectedElement && selectedElement.classList.contains("sh-doc-div")) {
            alert("Вы не можете делиться документом, к которому имеете общий доступ");
            return;
        }

        const shareTo = prompt("Укажите (через запятую и пробел) логины тех, с кем хотите поделиться доступом, например: user1, user2", "").trim().split(", ");
        if (shareTo.length === 0) return;
        const docId = currentlySelected;
        data = {
          id: docId,
          share_to: shareTo
        }
        asyncShareDoc(data);
      }

      
      const createDoc = () => {
        const docName = prompt("Укажите название нового файла", "Новый документ");
        if (!docName) return;

        data = {
          title: docName
        }
        asyncCreateDoc(data);
      }

      
      document.getElementById("open").onclick = openDoc;
      document.getElementById("delete").onclick = deleteDoc;
      document.getElementById("share").onclick = shareDoc;
      document.getElementById("create").onclick = createDoc;
      
      
      for (const doc of myDocs) {
        let docDiv = document.createElement("div");
        docDiv.classList.add("doc-div");
        docDiv.setAttribute("data-doc-id", doc.id);

        docDiv.onclick = () => {
            if (currentlySelected === doc.id) {
                docDiv.classList.remove("doc-selected");
                currentlySelected = null;
            } else {
                document.querySelectorAll(".doc-div").forEach((d) => {
                    d.classList.remove("doc-selected");
                });
                
                docDiv.classList.add("doc-selected");
                currentlySelected = doc.id;
                document.getElementById("panel-buttons").classList.add("panel-buttons-visible");
            }
        };

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
        docDiv.setAttribute("data-doc-id", doc.id);

        docDiv.onclick = () => {
          document.querySelectorAll(".doc-div, .sh-doc-div").forEach((d) => {
              d.classList.remove("doc-selected");
          });
          
          docDiv.classList.add("doc-selected");
          currentlySelected = doc.id;
        };

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
          const loggedUser = localStorage.getItem("logged");
          const body = {
            title: data.title,
            content: "",
            username: loggedUser
          }
          const resp = await fetch(`http://localhost:8000/documents`, {
              method: "POST",
              headers: {
                  "Content-Type": "application/json"
              },
              body: JSON.stringify(body)
          });
          if (!resp.ok) {
              const errorData = await resp.json().catch(() => ({}));
              throw new Error(errorData.detail || "Не удалось создать документ");
          }

          const newDoc = await resp.json();
          console.log("Документ создан:", newDoc);
          
          location.reload();

      } catch (err) {
          alert(err.message);
          console.error(err);
          throw err;
      }
  }



  async function asyncDeleteDoc(data) {
      try {
          const resp = await fetch(`http://localhost:8000/documents/${data.id}`, {
              method: "DELETE",
              headers: {
                  "Content-Type": "application/json"
              }
          });
          
          if (!resp.ok) {
              const errorData = await resp.json().catch(() => ({}));
              throw new Error(errorData.detail || "Не удалось удалить документ");
          }
          
          return await resp.json();
      } catch (err) {
          alert(err.message);
          console.error(err);
          throw err;
      }
  }


  async function asyncShareDoc(data) {
      try {

          const docId = data.id;
          const usernames = data.share_to;
          
          const userIds = [];
          for (const username of usernames) {
              const userResp = await fetch(`http://localhost:8000/users/username/${username}`);
              if (!userResp.ok) {
                  throw new Error(`Пользователь "${username}" не найден`);
              }
              const userData = await userResp.json();
              userIds.push(userData.id);
          }

          const body = {
            user_ids: userIds,
            permission: "edit"
          }
          const resp = await fetch(`http://localhost:8000/documents/${docId}/collaborators`, {
              method: "POST",
              headers: {
                  "Content-Type": "application/json"
              },
              body: JSON.stringify(body)
          });
          if (!resp.ok) {
              throw new Error("Не удалось поделиться доступом");
          }

          alert(`Успешно поделились документом с пользователями: ${usernames.join(", ")}`);

      } catch (err) {
          alert(err.message);
          console.error(err);
      }
  }
}