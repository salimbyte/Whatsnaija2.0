



let slideIndex = 1;

document.addEventListener('DOMContentLoaded', function() {
  if (document.querySelector('.mySlides')) showSlides(slideIndex);
});

function plusSlides(n) {
  showSlides((slideIndex += n));
}

function currentSlide(n) {
  showSlides((slideIndex = n));
}

function showSlides(n) {
  let i;
  let slides = document.getElementsByClassName("mySlides");
  let dots = document.getElementsByClassName("dot");
  if (n > slides.length) slideIndex = 1;
  if (n < 1) slideIndex = slides.length;

  for (i = 0; i < slides.length; i++) slides[i].style.display = "none";
  for (i = 0; i < dots.length; i++) dots[i].classList.remove("active");

  slides[slideIndex - 1].style.display = "block";
  if (dots[slideIndex - 1]) {
    dots[slideIndex - 1].classList.add("active");
    dots[slideIndex - 1].scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }

  var counter = document.getElementById("slide-counter");
  if (counter) counter.textContent = slideIndex + " / " + slides.length;
}






function zoomIMG(e) {
  var modal = document.getElementById("myModal");
  var modalImg = document.getElementById("img01");
  modal.style.display = "flex";
  modalImg.src = e.src;
  document.body.style.overflow = "hidden";
}

function zoomOut(e) {
  var modal = document.getElementById("myModal");
  var modalImg = document.getElementById("img01");
  modalImg.src = "";
  modal.style.display = "none";
  document.body.style.overflow = "";
}


function formatText(command) {
  // Works on the focused contenteditable editor — renders formatting visually
  document.execCommand(command, false, null);
}


document.addEventListener("click", function(event) {
  document.querySelectorAll(".dropdown-content").forEach(function(dropdownContent) {
    if (!dropdownContent.contains(event.target) && !event.target.classList.contains("dropbtn")) {
      dropdownContent.classList.remove("show");
    }
  });
});

// post like
document.addEventListener('DOMContentLoaded', function () {
  // for like
  var likeBtn = document.getElementById('likebtn');
  if (likeBtn) {
    likeBtn.addEventListener('click', function () {
      var postId = this.getAttribute('data-post-id');
      var postSlug = this.getAttribute('data-post-slug');
      var url = '/posts/' + postId + '/' + postSlug + '/like/';

      var xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('X-CSRFTOKEN', CSRF_TOKEN);

      xhr.onload = function () {
        if (xhr.status === 200) {
          var data = JSON.parse(xhr.responseText);

          if (data.action === 'liked') {
            likeBtn.classList.add('active');
          } else if (data.action === 'unliked') {
            likeBtn.classList.remove('active');
          }

          var likeCount = document.querySelector('.like-count');
          if (likeCount) {
            if (data.new_likes_count > 0) {
              likeCount.style.display = 'block';
              likeCount.textContent = data.new_likes_count;
            } else {
              likeCount.textContent = '';
              likeCount.style.display = 'none';
            }
          }

          if (data.second_action == 'undisliked') {
            var dislikeBtn = document.getElementById('dislikebtn');
            if (dislikeBtn) dislikeBtn.classList.remove('active');

            var dislikeCount = document.querySelector('.dislike-count');
            if (dislikeCount) {
              if (data.new_dislikes_count > 0) {
                dislikeCount.style.display = 'block';
                dislikeCount.textContent = data.new_dislikes_count;
              } else {
                dislikeCount.textContent = '';
                dislikeCount.style.display = 'none';
              }
            }
          }
        } else if (xhr.status === 401) {
          if (typeof showToast === 'function') showToast('Log in to vote', 'info');
        }
      };

      xhr.onerror = function () {
        console.error('Request failed');
      };

      xhr.send();
    });
  }

  // for dislike
  var dislikeBtn = document.getElementById('dislikebtn');
  if (dislikeBtn) {
    dislikeBtn.addEventListener('click', function () {
      var postId = this.getAttribute('data-post-id');
      var postSlug = this.getAttribute('data-post-slug');
      var url = '/posts/' + postId + '/' + postSlug + '/dislike/';

      var xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('X-CSRFTOKEN', CSRF_TOKEN);

      xhr.onload = function () {
        if (xhr.status === 200) {
          var data = JSON.parse(xhr.responseText);

          if (data.action === 'disliked') {
            dislikeBtn.classList.add('active');
          } else if (data.action === 'undisliked') {
            dislikeBtn.classList.remove('active');
          }

          var dislikeCount = document.querySelector('.dislike-count');
          if (dislikeCount) {
            if (data.new_dislikes_count > 0) {
              dislikeCount.style.display = 'block';
              dislikeCount.textContent = data.new_dislikes_count;
            } else {
              dislikeCount.textContent = '';
              dislikeCount.style.display = 'none';
            }
          }

          if (data.second_action == 'unliked') {
            var likeBtn = document.getElementById('likebtn');
            if (likeBtn) likeBtn.classList.remove('active');

            var likeCount = document.querySelector('.like-count');
            if (likeCount) {
              if (data.new_likes_count > 0) {
                likeCount.style.display = 'block';
                likeCount.textContent = data.new_likes_count;
              } else {
                likeCount.textContent = '';
                likeCount.style.display = 'none';
              }
            }
          }
        } else if (xhr.status === 401) {
          if (typeof showToast === 'function') showToast('Log in to vote', 'info');
        }
      };

      xhr.onerror = function () {
        console.error('Request failed');
      };

      xhr.send();
    });
  }
});

// comment like
function likeComment(element, csrf_token) {
  var commentId = element.getAttribute("data-comment-id");
  var postId = element.getAttribute("data-post-id");
  var url = `/posts/${postId}/comments/${commentId}/like/`;
  var xhr = new XMLHttpRequest();
  xhr.open("POST", url, true);
  xhr.setRequestHeader("Content-Type", "application/json");
  xhr.setRequestHeader("X-CSRFToken", CSRF_TOKEN);
  xhr.onreadystatechange = function () {
    if (xhr.readyState == 4 && xhr.status == 200) {
      var data = JSON.parse(xhr.responseText);
      var ct = element.querySelector('.c-like-ct');
      if (data.action === "liked") {
        element.classList.add("c-btn--liked");
        // remove dislike highlight from sibling dislike button
        var dislikeBtn = element.closest('.c-actions').querySelector('.c-btn--disliked');
        if (dislikeBtn) {
          dislikeBtn.classList.remove("c-btn--disliked");
          var ddct = dislikeBtn.querySelector('.c-dislike-ct');
          if (ddct && data.new_dislikes_count !== undefined) {
            if (data.new_dislikes_count > 0) { ddct.style.display = "inline"; ddct.textContent = data.new_dislikes_count; }
            else { ddct.style.display = "none"; ddct.textContent = ""; }
          }
        }
      } else if (data.action === "unliked") {
        element.classList.remove("c-btn--liked");
      }
      if (ct) {
        if (data.new_likes_count > 0) {
          ct.style.display = "inline";
          ct.textContent = data.new_likes_count;
        } else {
          ct.style.display = "none";
          ct.textContent = "";
        }
      }
    } else if (xhr.readyState == 4 && xhr.status == 401) {
      if (typeof showToast === 'function') showToast('Log in to vote', 'info');
    }
  };
  xhr.send();
}

function dislikeComment(element, csrf_token) {
  var commentId = element.getAttribute("data-comment-id");
  var postId = element.getAttribute("data-post-id");
  var url = `/posts/${postId}/comments/${commentId}/dislike/`;
  var xhr = new XMLHttpRequest();
  xhr.open("POST", url, true);
  xhr.setRequestHeader("Content-Type", "application/json");
  xhr.setRequestHeader("X-CSRFToken", CSRF_TOKEN);
  xhr.onreadystatechange = function () {
    if (xhr.readyState == 4 && xhr.status == 200) {
      var data = JSON.parse(xhr.responseText);
      var dct = element.querySelector('.c-dislike-ct');
      if (data.action === "disliked") {
        element.classList.add("c-btn--disliked");
        // remove like highlight from sibling like button
        var likeBtn = element.closest('.c-actions').querySelector('.c-btn--liked');
        if (likeBtn) {
          likeBtn.classList.remove("c-btn--liked");
          var lct = likeBtn.querySelector('.c-like-ct');
          if (lct && data.new_likes_count !== undefined) {
            if (data.new_likes_count > 0) { lct.style.display = "inline"; lct.textContent = data.new_likes_count; }
            else { lct.style.display = "none"; lct.textContent = ""; }
          }
        }
      } else {
        element.classList.remove("c-btn--disliked");
      }
      if (dct) {
        if (data.new_dislikes_count > 0) {
          dct.style.display = "inline";
          dct.textContent = data.new_dislikes_count;
        } else {
          dct.style.display = "none";
          dct.textContent = "";
        }
      }
    } else if (xhr.readyState == 4 && xhr.status == 401) {
      if (typeof showToast === 'function') showToast('Log in to vote', 'info');
    }
  };
  xhr.send();
}

/* ── Comment interactions (single definitions, replaces per-comment inline scripts) ── */
function toggleCommentMenu(id) {
  const menu = document.getElementById('comment-menu-' + id);
  document.querySelectorAll('[id^="comment-menu-"]').forEach(m => {
    if (m.id !== 'comment-menu-' + id) m.style.display = 'none';
  });
  if (menu) menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

function toggleReplyForm(id, username) {
  var form = document.getElementById('reply-form-' + id);
  if (!form) return;
  var isOpen = form.style.display !== 'none';
  // Close all other open reply forms
  document.querySelectorAll('.c-reply-form').forEach(function(f) {
    if (f.id !== 'reply-form-' + id) f.style.display = 'none';
  });
  form.style.display = isOpen ? 'none' : 'block';
  if (!isOpen) {
    var editor = document.getElementById('reply-editor-' + id);
    if (editor) {
      // @mention prefix for reply-to-reply context
      if (username) {
        var commentEl = document.getElementById('comment-' + id);
        if (commentEl && commentEl.classList.contains('comment--reply') && !editor.textContent.trim()) {
          editor.focus();
          document.execCommand('insertText', false, '@' + username + ' ');
        } else {
          editor.focus();
        }
      } else {
        editor.focus();
      }
      // Move cursor to end
      var range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(false);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }
  }
}

function highlightParentComment(parentId) {
  var el = document.getElementById('comment-' + parentId);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.remove('comment--highlight');
    void el.offsetWidth;  // force reflow to restart animation
    el.classList.add('comment--highlight');
    setTimeout(function() { el.classList.remove('comment--highlight'); }, 3000);
  }
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('[id^="comment-menu-"]') && !e.target.closest('[onclick*="toggleCommentMenu"]')) {
    document.querySelectorAll('[id^="comment-menu-"]').forEach(m => m.style.display = 'none');
  }
});

// Collapse repeated MOD badges for the same user to a small dot
function dedupModBadges(root) {
  root = root || document;
  var seen = root._seenMods || (root._seenMods = new Set());
  root.querySelectorAll('.c-mod:not(.c-mod--dot)').forEach(function(badge) {
    var byline = badge.closest('.c-byline');
    if (!byline) return;
    var author = byline.querySelector('.c-author');
    var username = author ? (author.textContent || '').trim() : null;
    if (!username) return;
    if (seen.has(username)) {
      badge.classList.add('c-mod--dot');
      badge.setAttribute('aria-label', 'MOD');
      badge.textContent = '';
    } else {
      seen.add(username);
    }
  });
}

document.addEventListener('DOMContentLoaded', function() { dedupModBadges(); });