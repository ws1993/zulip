import isUrl from "is-url";
import $ from "jquery";
import _ from "lodash";
import assert from "minimalistic-assert";
import {insertTextIntoField} from "text-field-edit";
import TurndownService from "turndown";

import * as compose_ui from "./compose_ui.ts";
import * as hash_util from "./hash_util.ts";
import * as message_lists from "./message_lists.ts";
import * as rows from "./rows.ts";
import * as stream_data from "./stream_data.ts";
import * as topic_link_util from "./topic_link_util.ts";
import * as util from "./util.ts";

declare global {
    // eslint-disable-next-line @typescript-eslint/consistent-type-definitions
    interface HTMLElementTagNameMap {
        math: HTMLElement;
        strike: HTMLElement;
    }
}

function find_boundary_tr(
    $initial_tr: JQuery,
    iterate_row: ($tr: JQuery) => JQuery,
): [number, boolean] | undefined {
    let j;
    let skip_same_td_check = false;
    let $tr = $initial_tr;

    // If the selection boundary is somewhere that does not have a
    // parent tr, we should let the browser handle the copy-paste
    // entirely on its own
    if ($tr.length === 0) {
        return undefined;
    }

    // If the selection boundary is on a table row that does not have an
    // associated message id (because the user clicked between messages),
    // then scan downwards until we hit a table row with a message id.
    // To ensure we can't enter an infinite loop, bail out (and let the
    // browser handle the copy-paste on its own) if we don't hit what we
    // are looking for within 10 rows.
    for (j = 0; !$tr.is(".message_row") && j < 10; j += 1) {
        $tr = iterate_row($tr);
    }
    if (j === 10) {
        return undefined;
    } else if (j !== 0) {
        // If we updated tr, then we are not dealing with a selection
        // that is entirely within one td, and we can skip the same td
        // check (In fact, we need to because it won't work correctly
        // in this case)
        skip_same_td_check = true;
    }
    return [rows.id($tr), skip_same_td_check];
}

function construct_recipient_header($message_row: JQuery): JQuery {
    const message_header_content = rows
        .get_message_recipient_header($message_row)
        .text()
        .replaceAll(/\s+/g, " ")
        .replace(/^\s/, "")
        .replace(/\s$/, "");
    return $("<p>").append($("<strong>").text(message_header_content));
}

/*
The techniques we use in this code date back to
2013 and may be obsolete today (and may not have
been even the best workaround back then).

https://github.com/zulip/zulip/commit/fc0b7c00f16316a554349f0ad58c6517ebdd7ac4

The idea is that we build a temp div, let jQuery process the
selection, then restore the selection on a zero-second timer back
to the original selection.

Do not be afraid to change this code if you understand
how modern browsers deal with copy/paste.  Just test
your changes carefully.
*/
function construct_copy_div($div: JQuery, start_id: number, end_id: number): void {
    if (message_lists.current === undefined) {
        return;
    }
    const copy_rows = rows.visible_range(start_id, end_id);

    const $start_row = copy_rows[0];
    assert($start_row !== undefined);
    const $start_recipient_row = rows.get_message_recipient_row($start_row);
    const start_recipient_row_id = rows.id_for_recipient_row($start_recipient_row);
    let should_include_start_recipient_header = false;
    let last_recipient_row_id = start_recipient_row_id;

    for (const $row of copy_rows) {
        const recipient_row_id = rows.id_for_recipient_row(rows.get_message_recipient_row($row));
        // if we found a message from another recipient,
        // it means that we have messages from several recipients,
        // so we have to add new recipient's bar to final copied message
        // and wouldn't forget to add start_recipient's bar at the beginning of final message
        if (recipient_row_id !== last_recipient_row_id) {
            construct_recipient_header($row).appendTo($div);
            last_recipient_row_id = recipient_row_id;
            should_include_start_recipient_header = true;
        }
        const message = message_lists.current.get(rows.id($row));
        assert(message !== undefined);
        const $content = $(message.content);
        $content.first().prepend(
            $("<span>")
                .text(message.sender_full_name + ": ")
                .contents(),
        );
        $div.append($content);
    }

    if (should_include_start_recipient_header) {
        construct_recipient_header($start_row).prependTo($div);
    }
}

function select_div($div: JQuery, selection: Selection): void {
    $div.css({
        position: "absolute",
        left: "-99999px",
        // Color and background is made according to "light theme"
        // exclusively here because when copying the content
        // into, say, Gmail compose box, the styles come along.
        // This is done to avoid copying the content with dark
        // background when using the app in dark theme.
        // We can avoid other custom styles since they are wrapped
        // inside another parent such as `.message_content`.
        color: "#333",
        background: "#FFF",
    }).attr("id", "copytempdiv");
    $("body").append($div);
    selection.selectAllChildren(util.the($div));
}

function remove_div(_div: JQuery, ranges: Range[]): void {
    window.setTimeout(() => {
        const selection = window.getSelection();
        assert(selection !== null);
        selection.removeAllRanges();

        for (const range of ranges) {
            selection.addRange(range);
        }

        $("#copytempdiv").remove();
    }, 0);
}

export function copy_handler(): void {
    // This is the main handler for copying message content via
    // `Ctrl+C` in Zulip (note that this is totally independent of the
    // "select region" copy behavior on Linux; that is handled
    // entirely by the browser, our HTML layout, and our use of the
    // no-select CSS classes).  We put considerable effort
    // into producing a nice result that pastes well into other tools.
    // Our user-facing specification is the following:
    //
    // * If the selection is contained within a single message, we
    //   want to just copy the portion that was selected, which we
    //   implement by letting the browser handle the Ctrl+C event.
    //
    // * Otherwise, we want to copy the bodies of all messages that
    //   were partially covered by the selection.

    const selection = window.getSelection();
    assert(selection !== null);
    const analysis = analyze_selection(selection);
    const ranges = analysis.ranges;
    const start_id = analysis.start_id;
    const end_id = analysis.end_id;
    const skip_same_td_check = analysis.skip_same_td_check;
    const $div = $("<div>");

    if (start_id === undefined || end_id === undefined || start_id > end_id) {
        // In this case either the starting message or the ending
        // message is not defined, so this is definitely not a
        // multi-message selection and we can let the browser handle
        // the copy.
        //
        // Also, if our logic is not sound about the selection range
        // (start_id > end_id), we let the browser handle the copy.
        //
        // NOTE: `startContainer (~ start_id)` and `endContainer (~ end_id)`
        // of a `Range` are always from top to bottom in the DOM tree, independent
        // of the direction of the selection.
        // TODO: Add a reference for this statement, I just tested
        // it in console for various selection directions and found this
        // to be the case not sure why there is no online reference for it.
        // eslint-disable-next-line @typescript-eslint/no-deprecated
        document.execCommand("copy");
        return;
    }

    if (!skip_same_td_check && start_id === end_id) {
        // Check whether the selection both starts and ends in the
        // same message.  If so, Let the browser handle this.
        // eslint-disable-next-line @typescript-eslint/no-deprecated
        document.execCommand("copy");
        return;
    }

    // We've now decided to handle the copy event ourselves.
    //
    // We construct a temporary div for what we want the copy to pick up.
    // We construct the div only once, rather than for each range as we can
    // determine the starting and ending point with more confidence for the
    // whole selection. When constructing for each `Range`, there is a high
    // chance for overlaps between same message ids, avoiding which is much
    // more difficult since we can get a range (start_id and end_id) for
    // each selection `Range`.
    construct_copy_div($div, start_id, end_id);

    // Select div so that the browser will copy it
    // instead of copying the original selection
    select_div($div, selection);
    // eslint-disable-next-line @typescript-eslint/no-deprecated
    document.execCommand("copy");
    remove_div($div, ranges);
}

export function analyze_selection(selection: Selection): {
    ranges: Range[];
    start_id: number | undefined;
    end_id: number | undefined;
    skip_same_td_check: boolean;
} {
    // Here we analyze our selection to determine if part of a message
    // or multiple messages are selected.
    //
    // Firefox and Chrome handle selection of multiple messages
    // differently. Firefox typically creates multiple ranges for the
    // selection, whereas Chrome typically creates just one.
    //
    // Our goal in the below loop is to compute and be prepared to
    // analyze the combined range of the selections, and copy their
    // full content.

    let i;
    let range;
    const ranges = [];
    let $startc;
    let $endc;
    let $initial_end_tr;
    let start_id;
    let end_id;
    let start_data;
    let end_data;
    // skip_same_td_check is true whenever we know for a fact that the
    // selection covers multiple messages (and thus we should no
    // longer consider letting the browser handle the copy event).
    let skip_same_td_check = false;

    for (i = 0; i < selection.rangeCount; i += 1) {
        range = selection.getRangeAt(i);
        ranges.push(range);

        $startc = $(range.startContainer);
        start_data = find_boundary_tr(
            $startc.parents(".selectable_row, .message_header").first(),
            ($row) => $row.next(),
        );
        if (start_data === undefined) {
            // Skip any selection sections that don't intersect a message.
            continue;
        }
        if (start_id === undefined) {
            // start_id is the Zulip message ID of the first message
            // touched by the selection.
            start_id = start_data[0];
        }

        $endc = $(range.endContainer);
        $initial_end_tr = get_end_tr_from_endc($endc);
        end_data = find_boundary_tr($initial_end_tr, ($row) => $row.prev());

        if (end_data === undefined) {
            // Skip any selection sections that don't intersect a message.
            continue;
        }
        if (end_data[0] !== undefined) {
            end_id = end_data[0];
        }

        if (start_data[1] || end_data[1]) {
            // If the find_boundary_tr call for either the first or
            // the last message covered by the selection
            skip_same_td_check = true;
        }
    }

    return {
        ranges,
        start_id,
        end_id,
        skip_same_td_check,
    };
}

function get_end_tr_from_endc($endc: JQuery<Node>): JQuery {
    if ($endc.attr("id") === "bottom_whitespace" || $endc.attr("id") === "compose_close") {
        // If the selection ends in the bottom whitespace, we should
        // act as though the selection ends on the final message.
        // This handles the issue that Chrome seems to like selecting
        // the compose_close button when you go off the end of the
        // last message
        return rows.last_visible();
    }

    // Sometimes (especially when three click selecting in Chrome) the selection
    // can end in a hidden element in e.g. the next message, a date divider.
    // We can tell this is the case because the selection isn't inside a
    // `messagebox-content` div, which is where the message text itself is.
    // TODO: Ideally make it so that the selection cannot end there.
    // For now, we find the message row directly above wherever the
    // selection ended.
    if ($endc.closest(".messagebox-content").length === 0) {
        // If the selection ends within the message following the selected
        // messages, go back to use the actual last message.
        if ($endc.parents(".message_row").length > 0) {
            const $parent_msg = $endc.parents(".message_row").first();
            return $parent_msg.prev(".message_row");
        }
        // If it's not in a .message_row, it's probably in a .message_header and
        // we can use the last message from the previous recipient_row.
        // NOTE: It is possible that the selection started and ended inside the
        // message header and in that case we would be returning the message before
        // the selected header if it exists, but that is not the purpose of this
        // function to handle.
        if ($endc.parents(".message_header").length > 0) {
            const $overflow_recipient_row = $endc.parents(".recipient_row").first();
            return $overflow_recipient_row.prev(".recipient_row").children(".message_row").last();
        }
        // If somehow we get here, do the default return.
    }

    return $endc.parents(".selectable_row").first();
}

function deduplicate_newlines(attribute: string): string {
    // We replace any occurrences of one or more consecutive newlines followed by
    // zero or more whitespace characters with a single newline character.
    return attribute ? attribute.replaceAll(/(\n+\s*)+/g, "\n") : "";
}

function image_to_zulip_markdown(
    _content: string,
    node: Element | Document | DocumentFragment,
): string {
    assert(node instanceof Element);
    if (node.nodeName === "IMG" && node.classList.contains("emoji") && node.hasAttribute("alt")) {
        // For Zulip's custom emoji
        return node.getAttribute("alt") ?? "";
    }
    const src = node.getAttribute("src") ?? node.getAttribute("href") ?? "";
    const title = deduplicate_newlines(node.getAttribute("title") ?? "");
    // Using Zulip's link like syntax for images
    return src ? "[" + title + "](" + src + ")" : (node.getAttribute("alt") ?? "");
}

function within_single_element(html_fragment: HTMLElement): boolean {
    return (
        html_fragment.childNodes.length === 1 &&
        html_fragment.firstElementChild !== null &&
        html_fragment.firstElementChild.innerHTML !== ""
    );
}

export function is_white_space_pre(paste_html: string): boolean {
    const html_fragment = new DOMParser()
        .parseFromString(paste_html, "text/html")
        .querySelector("body");
    assert(html_fragment !== null);
    return (
        within_single_element(html_fragment) &&
        html_fragment.firstElementChild instanceof HTMLElement &&
        html_fragment.firstElementChild.style.whiteSpace === "pre"
    );
}

function is_from_excel(html_fragment: HTMLBodyElement): boolean {
    const html_tag = html_fragment.parentElement;
    if (!html_tag || html_tag.nodeName !== "HTML") {
        return false;
    }

    const excel_namespaces = [
        "urn:schemas-microsoft-com:office:excel",
        "urn:schemas-microsoft-com:office:office",
    ];

    const has_excel_metadata = [...html_tag.querySelectorAll("meta")].some(
        (meta) =>
            (meta.name === "ProgId" && meta.content === "Excel.Sheet") ||
            (meta.name === "Generator" && meta.content?.includes("Microsoft Excel")),
    );
    if (!has_excel_metadata) {
        return false;
    }

    if (!html_tag.querySelector("[class^='xl']")) {
        return false;
    }

    const html_outer = html_tag.outerHTML;

    if (!html_outer.includes("<!--StartFragment-->")) {
        return false;
    }

    if (!excel_namespaces.some((ns) => html_outer.includes(ns))) {
        return false;
    }

    return true;
}

export function is_single_image(paste_html: string): boolean {
    const html_fragment = new DOMParser()
        .parseFromString(paste_html, "text/html")
        .querySelector("body");
    assert(html_fragment !== null);
    return (
        is_from_excel(html_fragment) ||
        (html_fragment.childNodes.length === 1 &&
            html_fragment.firstElementChild !== null &&
            html_fragment.firstElementChild.nodeName === "IMG")
    );
}

export function paste_handler_converter(
    paste_html: string,
    $textarea?: JQuery<HTMLTextAreaElement>,
): string {
    const copied_html_fragment = new DOMParser()
        .parseFromString(paste_html, "text/html")
        .querySelector("body");
    assert(copied_html_fragment !== null);

    const para_elements = copied_html_fragment.querySelectorAll("p");

    for (const element of para_elements) {
        const children = [...element.childNodes];
        /*
            The aim behind doing this is to convert the intermediate text nodes
            between two katex spans into spans.

            This is done because filter() function only processes HTMLElements
        */
        for (const child of children) {
            if (child.nodeType === Node.TEXT_NODE) {
                const span = document.createElement("span");
                span.classList.add("zulip-paste-parser-text-node");
                span.textContent = child.textContent;
                child.replaceWith(span);
            }
        }
    }

    const copied_within_single_element = within_single_element(copied_html_fragment);
    const outer_elements_to_retain = ["PRE", "UL", "OL", "A", "CODE"];
    // If the entire selection copied is within a single HTML element (like an
    // `h1`), we don't want to retain its styling, except when it is needed to
    // identify the intended structure of the copied content.
    if (
        copied_within_single_element &&
        copied_html_fragment.firstElementChild !== null &&
        !outer_elements_to_retain.includes(copied_html_fragment.firstElementChild.nodeName)
    ) {
        paste_html = copied_html_fragment.firstElementChild.innerHTML;
    }

    // turning off escaping (for now) to remove extra `/`
    TurndownService.prototype.escape = (string) => string;

    const turndownService = new TurndownService({
        emDelimiter: "*",
        codeBlockStyle: "fenced",
        headingStyle: "atx",
        br: "",
    });
    turndownService.addRule("style", {
        filter: "style",
        replacement() {
            return "";
        },
    });
    turndownService.addRule("strikethrough", {
        filter: ["del", "s", "strike"],
        replacement(content) {
            return "~~" + content + "~~";
        },
    });
    turndownService.addRule("links", {
        filter: ["a"],
        replacement(content, node) {
            assert(node instanceof HTMLAnchorElement);
            if (node.href === content) {
                // Checks for raw links without custom text.
                return content;
            }
            if (node.childNodes.length === 1 && node.firstChild!.nodeName === "IMG") {
                // ignore link's url if it only has an image
                return content;
            }
            return "[" + content + "](" + node.href + ")";
        },
    });
    turndownService.addRule("listItem", {
        // We override the original upstream implementation of this rule
        // to have a custom indent of 2 spaces for list items, instead of
        // the default 4 spaces. Everything else is the same as upstream.
        filter: "li",
        replacement(content, node) {
            content = content
                .replace(/^\n+/, "") // remove leading newlines
                .replace(/\n+$/, "\n") // replace trailing newlines with just a single one
                .replaceAll(/\n/gm, "\n  "); // custom 2 space indent
            let prefix = "* ";
            const parent = node.parentElement;
            assert(parent !== null);
            if (parent.nodeName === "OL") {
                const start = parent.getAttribute("start");
                const index = Array.prototype.indexOf.call(parent.children, node);
                prefix = (start ? Number(start) + index : index + 1) + ". ";
            }
            return prefix + content + (node.nextSibling && !content.endsWith("\n") ? "\n" : "");
        },
    });

    /*
        Below lies the the thought process behind the parsing for math blocks and inline math expressions.

        The general structure of the katex-displays i.e. math blocks is:
        <p>
            span.katex-display(start expression 1)
                span.katex
                    nested stuff we don't really care about while parsing
                        annotation(contains the expression)
            span.katex-display(start expression 2)
                (same as above)
        '
        '
        '
        </p>
        A katex-display is present for every expression that is separated by two or more newlines in md.
        We also have to adjust our markdown for empty katex-displays generated due to excessive newlines between two
        expressions.

        The trick in case of the math blocks is approving all the katex displays
        instead of just the first one.
        This helps prevent the remaining katex display texts being addressed as
        text nodes and getting appended to the end unnecessarily.
        Then in the replacement function only process the parent <p> tag's immediate children only once.
        See : https://github.com/user-attachments/files/18058052/katex-display-logic.pdf for an example.

        We make use of a set to keep track whether the parent p is already processed in both the cases.

        In case of inline math expressions, the structure is same as math blocks.
        Instead of katex-displays being the immediate children of p, we have span.katex or
        textnodes(which are converted into spans before parsing) as the immediate children.
        Newlines in markdown are translated into <br> instead of empty katex-displays here.

        For more information:
        https://chat.zulip.org/#narrow/channel/9-issues/topic/Replying.20to.20highlighted.20text.2C.20LaTeX.20is.20not.20preserved.20.2331608/near/1991687
    */

    const processed_math_block_parents = new Set();
    const processed_inline_math_block_parents = new Set();
    turndownService.addRule("katex-math-block", {
        filter(node) {
            if (
                node.classList.contains("katex-display") &&
                !node.closest(".katex-display > .katex-display")
            ) {
                return true;
            }

            return false;
        },
        replacement(content: string, node) {
            assert(node instanceof HTMLElement);
            let math_block_markdown = "```math\n";
            const parent = node.parentElement!;
            if (processed_math_block_parents.has(parent)) {
                return "";
            }
            processed_math_block_parents.add(parent);
            let consecutive_empty_display_count = 0;
            for (const child of parent.children) {
                const annotation_element = child.querySelector(
                    '.katex-mathml annotation[encoding="application/x-tex"]',
                );
                if (annotation_element?.textContent) {
                    const katex_source = annotation_element.textContent.trim();
                    math_block_markdown += katex_source + "\n\n";
                    consecutive_empty_display_count = 0;
                } else {
                    // Handling cases where math block is selected directly without any preceding text.
                    // The initial katex display doesn't have the annotation when selection is done in this manner.
                    if (
                        child.classList.contains("katex-display") &&
                        child.querySelector("math")?.textContent !== ""
                    ) {
                        math_block_markdown += content;
                        continue;
                    }
                    if (consecutive_empty_display_count === 0) {
                        math_block_markdown += "\n\n\n";
                    } else {
                        math_block_markdown += "\n\n";
                    }
                    consecutive_empty_display_count += 1;
                }
            }
            // Don't add extra newline at the end
            math_block_markdown = math_block_markdown.slice(0, -1);
            return (math_block_markdown += "```");
        },
    });
    const inlineTags = new Set(["em", "strong"]);

    function is_inline_tag(node: HTMLElement): boolean {
        return node.nodeType === 1 && inlineTags.has(node.tagName.toLowerCase());
    }

    turndownService.addRule("katex-inline-math", {
        filter(node) {
            // Allow the intermediate text blocks, so that they don't get appended to the end.
            if (node.classList.contains("zulip-paste-parser-text-node") || is_inline_tag(node)) {
                return true;
            }
            if (node.classList.contains("katex") && !node.classList.contains("katex-display")) {
                // Should explicitly be an inline expression
                const parent = node.parentElement;
                if (parent?.classList.contains("katex-display")) {
                    return false;
                }
                return true;
            }

            return false;
        },
        replacement(content, node: Node) {
            let parsed_inline_expression = "";
            if (node !== null) {
                const parent = node.parentElement!;
                if (processed_inline_math_block_parents.has(parent)) {
                    return "";
                }
                processed_inline_math_block_parents.add(parent);
                for (const child of parent.children) {
                    let is_strong_ele = false;
                    let is_emphasized_ele = false;
                    if (child.nodeName.toLocaleLowerCase() === "strong") {
                        is_strong_ele = true;
                        parsed_inline_expression += "**";
                    }
                    if (child.nodeName.toLocaleLowerCase() === "em") {
                        is_emphasized_ele = true;
                        parsed_inline_expression += "*";
                    }
                    if (child.nodeName === "BR") {
                        parsed_inline_expression += "\n";
                        continue;
                    }
                    const annotation_element = child.querySelector(
                        `.katex-mathml annotation[encoding="application/x-tex"]`,
                    );
                    if (annotation_element?.textContent) {
                        const katex_source = annotation_element.textContent;
                        parsed_inline_expression += `$$${katex_source}$$`;
                        continue;
                    }
                    if (child.classList.contains("katex")) {
                        parsed_inline_expression += `$$${content}$$`;
                        continue;
                    }
                    // It is a text node that is not between two katex spans
                    parsed_inline_expression += child.textContent;
                    if (is_strong_ele) {
                        parsed_inline_expression += "**";
                    }
                    if (is_emphasized_ele) {
                        parsed_inline_expression += "*";
                    }
                    continue;
                }
            }
            return parsed_inline_expression;
        },
    });

    turndownService.addRule("zulipImagePreview", {
        filter(node) {
            // select image previews in Zulip messages
            return (
                node.classList.contains("message_inline_image") && node.firstChild?.nodeName === "A"
            );
        },

        replacement(content, node) {
            // We parse the copied html to then check if the generating link (which, if
            // present, always comes before the preview in the copied html) is also there.

            // If the 1st element with the same image link in the copied html
            // does not have the `message_inline_image` class, it means it is the generating
            // link, and not the preview, meaning the generating link is copied as well.
            const copied_html = new DOMParser().parseFromString(paste_html, "text/html");
            let href;
            if (
                node.firstElementChild === null ||
                (href = node.firstElementChild.getAttribute("href")) === null ||
                !copied_html
                    .querySelector("a[href='" + CSS.escape(href) + "']")
                    ?.parentElement?.classList.contains("message_inline_image")
            ) {
                // We skip previews which have their generating link copied too, to avoid
                // double pasting the same link.
                return "";
            }
            return image_to_zulip_markdown(content, node.firstElementChild);
        },
    });
    turndownService.addRule("images", {
        filter: "img",

        replacement: image_to_zulip_markdown,
    });
    turndownService.addRule("math", {
        // We don't have a way to get the original LaTeX code from the rendered
        // `math` so we drop it to avoid pasting gibberish.
        // In the future, we could have a data-original-latex feature in Zulip HTML
        // if we wanted to paste the original LaTeX for Zulip messages.
        filter: "math",

        replacement() {
            return "";
        },
    });

    // We override the original upstream implementation of this rule to make
    // several tweaks:
    // - We turn any single line code blocks into inline markdown code.
    // - We generalise the filter condition to allow a `pre` element with a
    // `code` element as its only non-empty child, which applies to Zulip code
    // blocks too.
    // - For Zulip code blocks, we extract the language of the code block (if
    // any) correctly.
    // - We don't do any conversion to code blocks if the user seems to already
    // be trying to create a codeblock (i.e. the cursor in the composebox is
    // following a "`").
    // Everything else works the same.
    turndownService.addRule("fencedCodeBlock", {
        filter(node, options) {
            let text_children;
            return (
                options.codeBlockStyle === "fenced" &&
                node.nodeName === "PRE" &&
                (text_children = [...node.childNodes].filter(
                    (child) => child.textContent !== null && child.textContent.trim() !== "",
                )).length === 1 &&
                text_children[0]?.nodeName === "CODE"
            );
        },

        replacement(content, node, options) {
            assert(node instanceof HTMLElement);
            const codeElement = [...node.children].find((child) => child.nodeName === "CODE");
            assert(codeElement !== undefined);
            const code = codeElement.textContent;
            assert(code !== null);

            // We convert single line code inside a code block to inline markdown code,
            // and the code for this is taken from upstream's `code` rule.
            if (!code.includes("\n")) {
                // If the cursor is just after a backtick, then we don't add extra backticks.
                if (
                    $textarea &&
                    $textarea.caret() !== 0 &&
                    $textarea.val()?.at($textarea.caret() - 1) === "`"
                ) {
                    return content;
                }
                if (!code) {
                    return "";
                }
                const extraSpace = /^`|^ .*?[^ ].* $|`$/.test(code) ? " " : "";

                // Pick the shortest sequence of backticks that is not found in the code
                // to be the delimiter.
                let delimiter = "`";
                const matches: string[] = code.match(/`+/gm) ?? [];
                while (matches.includes(delimiter)) {
                    delimiter = delimiter + "`";
                }

                return delimiter + extraSpace + code + extraSpace + delimiter;
            }

            const className = codeElement.getAttribute("class") ?? "";
            const language = node.parentElement?.classList.contains("zulip-code-block")
                ? (node.closest<HTMLElement>(".codehilite")?.dataset?.codeLanguage ?? "")
                : (/language-(\S+)/.exec(className) ?? [null, ""])[1];

            assert(options.fence !== undefined);
            const fenceChar = options.fence.charAt(0);
            let fenceSize = 3;
            const fenceInCodeRegex = new RegExp("^" + fenceChar + "{3,}", "gm");

            let match;
            while ((match = fenceInCodeRegex.exec(code))) {
                if (match[0].length >= fenceSize) {
                    fenceSize = match[0].length + 1;
                }
            }

            const fence = fenceChar.repeat(fenceSize);

            return (
                "\n\n" + fence + language + "\n" + code.replace(/\n$/, "") + "\n" + fence + "\n\n"
            );
        },
    });
    let markdown_text = turndownService.turndown(paste_html);

    // Checks for escaped ordered list syntax.
    markdown_text = markdown_text.replaceAll(/^(\W* {0,3})(\d+)\\\. /gm, "$1$2. ");

    // Removes newlines before the start of a list and between list elements.
    markdown_text = markdown_text.replaceAll(/\n+([*+-])/g, "\n$1");
    return markdown_text;
}

function is_safe_url_paste_target($textarea: JQuery<HTMLTextAreaElement>): boolean {
    const range = $textarea.range();

    if (!range.text) {
        // No range is selected
        return false;
    }

    if (isUrl(range.text.trim())) {
        // Don't engage our URL paste logic over existing URLs
        return false;
    }

    if (range.start <= 2) {
        // The range opens too close to the start of the textarea
        // to have to worry about Markdown link syntax
        return true;
    }

    // Look at the two characters before the start of the original
    // range in search of the tell-tale `](` from existing Markdown
    // link syntax
    if (cursor_at_markdown_link_marker($textarea)) {
        return false;
    }

    return true;
}

export function cursor_at_markdown_link_marker($textarea: JQuery<HTMLTextAreaElement>): boolean {
    const range = $textarea.range();
    const possible_markdown_link_markers = util
        .the($textarea)
        .value.slice(range.start - 2, range.start);
    return possible_markdown_link_markers === "](";
}

export function maybe_transform_html(html: string, text: string): string {
    if (is_white_space_pre(html)) {
        // Copied content styled with `white-space: pre` is pasted as is
        // but formatted as code. We need this for content copied from
        // VS Code like sources.
        return "<pre><code>" + _.escape(text) + "</code></pre>";
    }
    return html;
}

function add_text_and_select(text: string, $textarea: JQuery<HTMLTextAreaElement>): void {
    const textarea = $textarea.get(0);
    assert(textarea instanceof HTMLTextAreaElement);
    const init_cursor_pos = textarea.selectionStart;
    insertTextIntoField(textarea, text);
    const new_cursor_pos = textarea.selectionStart;
    textarea.setSelectionRange(init_cursor_pos, new_cursor_pos);
}

export function try_stream_topic_syntax_text(text: string): string | null {
    const stream_topic = hash_util.decode_stream_topic_from_url(text);

    if (!stream_topic) {
        return null;
    }

    // Now we're sure that the URL is a valid stream topic URL.
    // But the produced #**stream>topic** syntax could be broken.

    const stream = stream_data.get_sub_by_id(stream_topic.stream_id);
    assert(stream !== undefined);
    const stream_name = stream.name;
    if (topic_link_util.will_produce_broken_stream_topic_link(stream_name)) {
        return topic_link_util.get_fallback_markdown_link(
            stream_name,
            stream_topic.topic_name,
            stream_topic.message_id,
        );
    }

    if (
        stream_topic.topic_name !== undefined &&
        topic_link_util.will_produce_broken_stream_topic_link(stream_topic.topic_name)
    ) {
        return topic_link_util.get_fallback_markdown_link(
            stream_name,
            stream_topic.topic_name,
            stream_topic.message_id,
        );
    }

    let syntax_text = "#**" + stream_name;
    if (stream_topic.topic_name !== undefined) {
        syntax_text += ">" + stream_topic.topic_name;
    }

    if (stream_topic.message_id !== undefined) {
        syntax_text += "@" + stream_topic.message_id;
    }

    syntax_text += "**";
    return syntax_text;
}

export function paste_handler(this: HTMLTextAreaElement, event: JQuery.TriggeredEvent): void {
    assert(event.originalEvent instanceof ClipboardEvent);
    const clipboardData = event.originalEvent.clipboardData;
    if (!clipboardData) {
        // On IE11, ClipboardData isn't defined.  One can instead
        // access it with `window.clipboardData`, but even that
        // doesn't support text/html, so this code path couldn't do
        // anything special anyway.  So we instead just let the
        // default paste handler run on IE11.
        return;
    }

    if (clipboardData.getData) {
        const $textarea = $(this);
        const paste_text = clipboardData.getData("text");
        let paste_html = clipboardData.getData("text/html");
        // Trim the paste_text to accommodate sloppy copying
        const trimmed_paste_text = paste_text.trim();

        // Only intervene to generate formatted links when dealing
        // with a URL and a URL-safe range selection.
        if (isUrl(trimmed_paste_text)) {
            if (is_safe_url_paste_target($textarea)) {
                event.preventDefault();
                event.stopPropagation();
                const url = trimmed_paste_text;
                compose_ui.format_text($textarea, "linked", url);
                return;
            }

            if (
                !compose_ui.cursor_inside_code_block($textarea) &&
                !cursor_at_markdown_link_marker($textarea) &&
                !compose_ui.shift_pressed
            ) {
                // Try to transform the url to #**stream>topic** syntax
                // if it is a valid url.
                const syntax_text = try_stream_topic_syntax_text(trimmed_paste_text);
                if (syntax_text) {
                    event.preventDefault();
                    event.stopPropagation();
                    // To ensure you can get the actual pasted URL back via the browser
                    // undo feature, we first paste the URL in, then select it, and then
                    // replace it with the nicer markdown syntax.
                    add_text_and_select(trimmed_paste_text, $textarea);
                    compose_ui.insert_and_scroll_into_view(syntax_text + " ", $textarea);
                }
                return;
            }
        }
        // We do not paste formatted markdown when inside a code block.
        // Unlike Chrome, Firefox doesn't automatically paste plainly on using Ctrl+Shift+V,
        // hence we need to handle it ourselves, by checking if shift key is pressed, and only
        // if not, we proceed with the default formatted paste.
        if (
            !compose_ui.cursor_inside_code_block($textarea) &&
            paste_html &&
            !compose_ui.shift_pressed
        ) {
            if (is_single_image(paste_html)) {
                // If the copied content is a single image, we let upload.ts handle it.
                return;
            }
            event.preventDefault();
            event.stopPropagation();
            paste_html = maybe_transform_html(paste_html, paste_text);
            const text = paste_handler_converter(paste_html, $textarea);
            if (trimmed_paste_text !== text) {
                // Pasting formatted text is a two-step process: First
                // we paste unformatted text, then overwrite it with
                // formatted text, so that undo restores the
                // pre-formatting syntax.
                add_text_and_select(trimmed_paste_text, $textarea);
            }
            compose_ui.insert_and_scroll_into_view(text, $textarea);
        }
    }
}

export function initialize(): void {
    $<HTMLTextAreaElement>("textarea#compose-textarea").on("paste", paste_handler);
    $("body").on("paste", "textarea.message_edit_content", paste_handler);
}
