// Renders journal markdown, only allowing images hosted on our own upload bucket.
// Anything else is swapped for a notice with a link to the original.
(function () {
    const allowedImageBase = (document.currentScript?.dataset.allowedImageBase || "").replace(/\/+$/, "");

    function isAllowedImage(src) {
        if (!allowedImageBase) {
            return false;
        }
        try {
            const url = new URL(src, window.location.href);
            return url.href.startsWith(`${allowedImageBase}/`);
        } catch (e) {
            return false;
        }
    }

    function isSafeLink(src) {
        try {
            const url = new URL(src, window.location.href);
            return url.protocol === "https:" || url.protocol === "http:";
        } catch (e) {
            return false;
        }
    }

    function externalImageNotice(img) {
        const src = img.getAttribute("src") || "";

        const notice = document.createElement("span");
        notice.className =
            "my-2 flex flex-wrap items-center gap-x-2 gap-y-1 border border-dashed border-border bg-card px-3 py-2 text-sm text-muted-foreground";

        notice.insertAdjacentHTML(
            "beforeend",
            '<svg class="size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 19.5h16.5a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 6v12a1.5 1.5 0 0 0 1.5 1.5Z"></path><path d="M3 3l18 18"></path></svg>',
        );

        const label = document.createElement("span");
        label.textContent = "External images are not supported.";
        notice.append(label);

        if (src && isSafeLink(src)) {
            const link = document.createElement("a");
            link.href = src;
            link.target = "_blank";
            link.rel = "noreferrer";
            link.className = "text-primary underline hover:text-accent";
            link.textContent = "View original";
            notice.append(link);
        }

        return notice;
    }

    function placeholderNotice(img) {
        // Empty-src images are upload placeholders like "Uploading..." or "Error: ...".
        const notice = document.createElement("span");
        notice.className = "my-2 block border border-dashed border-border bg-card px-3 py-2 text-sm text-muted-foreground";
        notice.textContent = img.getAttribute("alt") || "Image";
        return notice;
    }

    window.renderJournalMarkdown = function (content, target) {
        // Build inside an inert <template> so blocked images are never fetched.
        const template = document.createElement("template");
        template.innerHTML = DOMPurify.sanitize(marked.parse(content));

        template.content.querySelectorAll("img").forEach(function (img) {
            const src = img.getAttribute("src") || "";
            if (!src.trim()) {
                img.replaceWith(placeholderNotice(img));
            } else if (!isAllowedImage(src)) {
                img.replaceWith(externalImageNotice(img));
            }
        });

        template.content.querySelectorAll("a[href]").forEach(function (link) {
            link.setAttribute("target", "_blank");
            link.setAttribute("rel", "noreferrer");
        });

        target.replaceChildren(template.content);
    };
})();
