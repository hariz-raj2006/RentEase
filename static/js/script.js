/* RentEase client-side script.
   Every feature below matches a hook in the templates:
   1 Mobile menu · 2 Flash close · 3 Image fallback · 4 Gallery · 5 Form validation
   6 Confirm delete · 7 Filter forms · 8 Image picker · 9 Wishlist (fetch)
   10 Counters · 11 Toast helper */
(function () {
  "use strict";

  // ---------------------------------------------------------------- helpers
  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  var toastTimer = null;
  function showToast(message, isError) {
    var toast = document.getElementById("toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "toast";
      toast.className = "toast";
      toast.setAttribute("role", "status");
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.toggle("toast-error", !!isError);
    // force reflow so the CSS transition always runs
    void toast.offsetWidth;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("show"); }, 2600);
  }

  // ------------------------------------------------- 1. mobile navigation
  var navToggle = document.getElementById("nav-toggle");
  var navMenu = document.getElementById("nav-menu");

  function setMenu(open) {
    navMenu.classList.toggle("open", open);
    navToggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (navToggle && navMenu) {
    navToggle.addEventListener("click", function () {
      setMenu(!navMenu.classList.contains("open"));
    });
    navMenu.addEventListener("click", function (e) {
      if (e.target.closest("a")) setMenu(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setMenu(false);
    });
    window.addEventListener("resize", function () {
      if (window.innerWidth > 900) setMenu(false);
    });
  }

  // ------------------------------------------------------ 2. flash close
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".flash-close");
    if (btn) {
      var flash = btn.closest(".flash");
      if (flash) flash.remove();
    }
  });
  // success messages fade away on their own after a few seconds
  document.querySelectorAll(".flash-success").forEach(function (el) {
    setTimeout(function () { if (el.isConnected) el.remove(); }, 6000);
  });

  // --------------------------------------------------- 3. image fallback
  // A small inline SVG used when a picture cannot be loaded.
  var PLACEHOLDER = "data:image/svg+xml;utf8," + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400">' +
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
    '<stop offset="0" stop-color="#cfe3ee"/><stop offset="1" stop-color="#e8f3f1"/></linearGradient></defs>' +
    '<rect width="640" height="400" fill="url(#g)"/>' +
    '<path d="M240 230 320 160l80 70v70h-52v-48h-56v48h-52z" fill="#0b1f3a" opacity=".35"/>' +
    '<text x="320" y="345" text-anchor="middle" font-family="Arial,sans-serif" font-size="22" fill="#0b1f3a" opacity=".5">Image not available</text>' +
    "</svg>"
  );

  function useFallback(img) {
    if (img.dataset.fallback === "1") return;     // avoid an endless error loop
    img.dataset.fallback = "1";
    img.src = PLACEHOLDER;
  }

  // "error" events do not bubble, but they can be caught in the capture phase
  document.addEventListener("error", function (e) {
    var img = e.target;
    if (img && img.tagName === "IMG" && img.classList.contains("js-img-fallback")) {
      useFallback(img);
    }
  }, true);

  // when a real image loads later (for example after changing the URL), allow fallback again
  document.addEventListener("load", function (e) {
    var img = e.target;
    if (img && img.tagName === "IMG" && img.src !== PLACEHOLDER) {
      delete img.dataset.fallback;
    }
  }, true);

  // Pictures that failed BEFORE this script started running
  document.querySelectorAll("img.js-img-fallback").forEach(function (img) {
    if (img.complete && img.naturalWidth === 0 && img.getAttribute("src")) {
      useFallback(img);
    }
  });

  // -------------------------------------------- 4. property image gallery
  var galleryMain = document.getElementById("gallery-main");
  document.querySelectorAll(".gallery-thumb").forEach(function (thumb) {
    thumb.addEventListener("click", function () {
      if (!galleryMain) return;
      delete galleryMain.dataset.fallback;
      galleryMain.src = thumb.dataset.src;
      document.querySelectorAll(".gallery-thumb").forEach(function (t) {
        t.classList.remove("active");
      });
      thumb.classList.add("active");
    });
  });

  // ------------------------------------------------ 5. form validation
  function messageFor(input) {
    var v = input.validity;
    var label = (input.labels && input.labels[0]) ? input.labels[0].textContent.trim() : "This field";

    if (v.valueMissing) return label + " is required.";
    if (v.typeMismatch) {
      return input.type === "email" ? "Enter a valid email address." : "Enter a valid value.";
    }
    if (v.tooShort) return label + " must be at least " + input.minLength + " characters.";
    if (v.tooLong) return label + " must be at most " + input.maxLength + " characters.";
    if (v.rangeUnderflow) return label + " must be at least " + input.min + ".";
    if (v.rangeOverflow) return label + " must be at most " + input.max + ".";
    if (v.patternMismatch) return input.title || "Please match the requested format.";
    if (v.customError) return input.validationMessage;
    return "Please check this field.";
  }

  function checkMatch(input) {
    // data-match="#password" means: this field must equal the field with that selector
    var selector = input.dataset.match;
    if (!selector) return;
    var other = document.querySelector(selector);
    if (other && input.value && input.value !== other.value) {
      input.setCustomValidity("Passwords do not match.");
    } else {
      input.setCustomValidity("");
    }
  }

  function validateField(input) {
    var wrapper = input.closest(".field");
    var errorBox = wrapper ? wrapper.querySelector(".field-error") : null;
    checkMatch(input);

    var ok = input.checkValidity();
    if (wrapper && errorBox) {
      wrapper.classList.toggle("has-error", !ok);
      wrapper.classList.toggle("is-valid", ok && input.value !== "");
      errorBox.textContent = ok ? "" : messageFor(input);
    }
    return ok;
  }

  document.querySelectorAll("form.js-validate").forEach(function (form) {
    var fields = form.querySelectorAll("input, select, textarea");

    fields.forEach(function (input) {
      if (input.type === "hidden" || input.type === "radio" || input.type === "checkbox") return;
      input.addEventListener("blur", function () { if (input.value !== "") validateField(input); });
      input.addEventListener("input", function () {
        var wrapper = input.closest(".field");
        // once an error is showing, re-check on every keystroke so it clears quickly
        if (wrapper && wrapper.classList.contains("has-error")) validateField(input);
        // typing in the password box must also re-check the confirm box
        if (form.querySelector('[data-match="#' + input.id + '"]')) {
          var confirmBox = form.querySelector('[data-match="#' + input.id + '"]');
          if (confirmBox.value) validateField(confirmBox);
        }
      });
    });

    form.addEventListener("submit", function (e) {
      var firstBad = null;
      fields.forEach(function (input) {
        if (input.type === "hidden") return;
        if (!validateField(input) && !firstBad) firstBad = input;
      });
      if (firstBad) {
        e.preventDefault();
        firstBad.focus();
        showToast("Please fix the highlighted fields.", true);
        return;
      }
      // stop double-clicks from sending the form twice
      var submit = form.querySelector('button[type="submit"]');
      if (submit) {
        setTimeout(function () { submit.disabled = true; }, 0);
      }
    });
  });

  // Re-enable submit buttons if the user comes back with the browser Back button
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) {
      document.querySelectorAll("form.js-validate button[type=submit]").forEach(function (b) {
        b.disabled = false;
      });
    }
  });

  // ------------------------------------------ 6. confirm before deleting
  document.querySelectorAll("form.js-confirm-form").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      var text = form.dataset.confirm || "Are you sure?";
      if (!window.confirm(text)) e.preventDefault();
    });
  });

  // ------------------------------------------------- 7. filter forms
  document.querySelectorAll("form.js-filter-form").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      var minBox = form.querySelector('[name="min_rent"]');
      var maxBox = form.querySelector('[name="max_rent"]');

      if (minBox && maxBox && minBox.value !== "" && maxBox.value !== "" &&
          Number(minBox.value) > Number(maxBox.value)) {
        e.preventDefault();
        showToast("Minimum rent cannot be higher than maximum rent.", true);
        maxBox.focus();
        return;
      }

      // Do not send empty fields, so the address bar stays short and clean
      form.querySelectorAll("input, select").forEach(function (el) {
        if (el.value === "" && el.name) {
          el.disabled = true;
          el.dataset.tempDisabled = "1";
        }
      });
    });
  });

  // Undo the temporary "disabled" if the user presses the Back button
  window.addEventListener("pageshow", function () {
    document.querySelectorAll('[data-temp-disabled="1"]').forEach(function (el) {
      el.disabled = false;
      delete el.dataset.tempDisabled;
    });
  });

  // The sort dropdown applies itself as soon as it changes
  document.querySelectorAll("select[data-autosubmit]").forEach(function (select) {
    select.addEventListener("change", function () {
      var form = select.form;
      if (!form) return;
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.submit();
    });
  });

  // ---------------------------------------- 8. sample image picker (owner)
  document.querySelectorAll("select[data-image-target]").forEach(function (select) {
    var target = document.querySelector(select.dataset.imageTarget);
    var preview = document.querySelector(select.dataset.imagePreview);
    if (!target) return;

    function updatePreview() {
      if (!preview) return;
      delete preview.dataset.fallback;
      preview.src = target.value.trim() || select.options[1].value;
    }

    select.addEventListener("change", function () {
      if (select.value) {
        target.value = select.value;
        updatePreview();
      }
    });
    target.addEventListener("change", updatePreview);
  });

  // ------------------------------- 9. wishlist (saved in MongoDB by Flask)
  document.querySelectorAll("form.wishlist-form").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();                       // we send it with fetch instead
      var button = form.querySelector(".wishlist-btn");
      var label = form.querySelector(".wishlist-label");
      if (button) button.disabled = true;

      fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-Requested-With": "fetch",
          "X-CSRFToken": csrfToken(),
          "Accept": "application/json"
        },
        body: new FormData(form)
      })
        .then(function (response) {
          var type = response.headers.get("content-type") || "";
          if (type.indexOf("application/json") === -1) {
            throw new Error("not-json");         // e.g. a CSRF error page
          }
          return response.json().then(function (data) {
            return { status: response.status, data: data };
          });
        })
        .then(function (result) {
          var data = result.data;

          if (result.status === 401 && data.login_url) {
            window.location.href = data.login_url;
            return;
          }
          if (!data.ok) {
            showToast(data.message || "Something went wrong.", true);
            return;
          }

          if (button) {
            button.classList.toggle("is-saved", data.wishlisted);
            button.setAttribute("aria-pressed", data.wishlisted ? "true" : "false");
          }
          if (label) label.textContent = data.wishlisted ? "♥ Saved" : "♡ Add to Wishlist";
          showToast(data.message, false);

          // On the wishlist page, an un-saved property disappears from the grid
          if (!data.wishlisted && form.dataset.removeCard === "true") {
            var card = form.closest(".property-card");
            if (card) card.remove();
            var grid = document.getElementById("wishlist-grid");
            var empty = document.getElementById("wishlist-empty");
            if (grid && grid.children.length === 0) {
              grid.classList.add("is-hidden");
              if (empty) empty.classList.remove("is-hidden");
              var counter = document.querySelector(".results-count");
              if (counter) counter.classList.add("is-hidden");
            }
          }
        })
        .catch(function () {
          // Fallback: submit normally so the server still handles it
          form.submit();
        })
        .finally(function () {
          if (button && button.isConnected) button.disabled = false;
        });
    });
  });

  // ----------------------------------------------- 10. animated counters
  var counters = document.querySelectorAll("[data-count]");
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function runCounter(el) {
    var end = parseInt(el.dataset.count, 10);
    if (isNaN(end) || end <= 0 || reduceMotion) return;
    var duration = 1200;
    var start = null;
    function step(time) {
      if (start === null) start = time;
      var progress = Math.min((time - start) / duration, 1);
      el.textContent = Math.floor(progress * end);
      if (progress < 1) requestAnimationFrame(step);
      else el.textContent = end;
    }
    requestAnimationFrame(step);
  }

  if (counters.length) {
    if ("IntersectionObserver" in window) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            runCounter(entry.target);
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0.4 });
      counters.forEach(function (el) { observer.observe(el); });
    }
    // Without IntersectionObserver the real numbers simply stay as written in the HTML.
  }
})();