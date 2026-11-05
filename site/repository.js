(function () {
  const repositoryUrl = window.RSLM_REPOSITORY_URL;
  const branch = window.RSLM_BRANCH || "main";

  document.querySelectorAll(".repository-link").forEach((link) => {
    if (repositoryUrl) {
      link.href = repositoryUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.removeAttribute("aria-disabled");
    } else {
      link.href = "#";
      link.setAttribute("aria-disabled", "true");
      link.addEventListener("click", (event) => event.preventDefault());
    }
  });

  document.querySelectorAll(".readme-link").forEach((link) => {
    if (repositoryUrl) {
      const readme = link.dataset.language === "en" ? "README.en.md" : "README.md";
      link.href = `${repositoryUrl}/blob/${encodeURIComponent(branch)}/${readme}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    } else {
      link.href = "#";
      link.setAttribute("aria-disabled", "true");
      link.addEventListener("click", (event) => event.preventDefault());
    }
  });

  document.querySelectorAll(".license-link").forEach((link) => {
    if (repositoryUrl) {
      link.href = `${repositoryUrl}/blob/${encodeURIComponent(branch)}/LICENSE`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    } else {
      link.href = "#";
      link.setAttribute("aria-disabled", "true");
      link.addEventListener("click", (event) => event.preventDefault());
    }
  });

  document.querySelectorAll(".documentation-link").forEach((link) => {
    if (repositoryUrl) {
      const documentPath = link.dataset.document;
      link.href = `${repositoryUrl}/blob/${encodeURIComponent(branch)}/${documentPath}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    } else {
      link.href = "#";
      link.setAttribute("aria-disabled", "true");
      link.addEventListener("click", (event) => event.preventDefault());
    }
  });
})();
