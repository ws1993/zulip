import $ from "jquery";

import * as blueslip from "./blueslip.ts";
import * as overlay_util from "./overlay_util.ts";

type Hook = () => void;

type OverlayOptions = {
    name: string;
    $overlay: JQuery;
    on_close: () => void;
};

type Overlay = {
    $element: JQuery;
    close_handler: () => void;
};

let active_overlay: Overlay | undefined;
let open_overlay_name: string | undefined;

const pre_open_hooks: Hook[] = [];
const pre_close_hooks: Hook[] = [];

function reset_state(): void {
    active_overlay = undefined;
    open_overlay_name = undefined;
}

export function register_pre_open_hook(func: Hook): void {
    pre_open_hooks.push(func);
}

export function register_pre_close_hook(func: Hook): void {
    pre_close_hooks.push(func);
}

function call_hooks(func_list: Hook[]): void {
    for (const element of func_list) {
        element();
    }
}

export function any_active(): boolean {
    return Boolean(open_overlay_name);
}

export function info_overlay_open(): boolean {
    return open_overlay_name === "informationalOverlays";
}

export function settings_open(): boolean {
    return open_overlay_name === "settings";
}

export function streams_open(): boolean {
    return open_overlay_name === "subscriptions";
}

export function groups_open(): boolean {
    return open_overlay_name === "group_subscriptions";
}

export function lightbox_open(): boolean {
    return open_overlay_name === "lightbox";
}

export function drafts_open(): boolean {
    return open_overlay_name === "drafts";
}

export function scheduled_messages_open(): boolean {
    return open_overlay_name === "scheduled";
}

export function message_edit_history_open(): boolean {
    return open_overlay_name === "message_edit_history";
}

export function open_overlay(opts: OverlayOptions): void {
    call_hooks(pre_open_hooks);

    if (!opts.name || !opts.$overlay || !opts.on_close) {
        blueslip.error("Programming error in open_overlay");
        return;
    }

    if (active_overlay !== undefined || open_overlay_name) {
        blueslip.error("Programming error - trying to open overlay before closing other", {
            name: opts.name,
            open_overlay_name,
        });
        return;
    }

    blueslip.debug("open overlay: " + opts.name);

    // Our overlays are kind of crufty...we have an HTML id
    // attribute for them and then a data-overlay attribute for
    // them.  Make sure they match.
    if (opts.$overlay.attr("data-overlay") !== opts.name) {
        blueslip.error("Bad overlay setup for " + opts.name);
        return;
    }

    open_overlay_name = opts.name;
    active_overlay = {
        $element: opts.$overlay,
        close_handler() {
            opts.on_close();
            reset_state();
        },
    };
    if (document.activeElement) {
        $(document.activeElement).trigger("blur");
    }
    overlay_util.disable_scrolling();
    opts.$overlay.addClass("show");
    opts.$overlay.attr("aria-hidden", "false");
    $(".app").attr("aria-hidden", "true");
    $("#navbar-fixed-container").attr("aria-hidden", "true");
}

export function close_overlay(name: string): void {
    call_hooks(pre_close_hooks);

    if (name !== open_overlay_name) {
        blueslip.error("Trying to close overlay with another open", {name, open_overlay_name});
        return;
    }

    if (name === undefined) {
        blueslip.error("Undefined name was passed into close_overlay");
        return;
    }

    if (active_overlay === undefined) {
        blueslip.error("close_overlay called without checking any_active()");
        return;
    }

    blueslip.debug("close overlay: " + name);
    active_overlay.$element.removeClass("show");

    active_overlay.$element.attr("aria-hidden", "true");
    $(".app").attr("aria-hidden", "false");
    $("#navbar-fixed-container").attr("aria-hidden", "false");

    active_overlay.close_handler();
    overlay_util.enable_scrolling();
}

export function close_active(): void {
    if (!open_overlay_name) {
        blueslip.warn("close_active() called without checking any_active()");
        return;
    }

    close_overlay(open_overlay_name);
}

export function close_for_hash_change(): void {
    if (open_overlay_name) {
        close_overlay(open_overlay_name);
    }
}

export function initialize(): void {
    $("body").on("click", "div.overlay, div.overlay .exit", (e) => {
        let $target = $(e.target);

        if (document.getSelection()?.type === "Range") {
            return;
        }

        // if the target is not the div.overlay element, search up the node tree
        // until it is found.
        if ($target.is(".exit, .exit-sign, .overlay-content, .exit span")) {
            $target = $target.closest("[data-overlay]");
        } else if (!$target.is("div.overlay")) {
            // not a valid click target then.
            return;
        }

        if ($target.data("noclose")) {
            // This overlay has been marked explicitly to not be closed.
            return;
        }

        const target_name = $target.attr("data-overlay")!;

        close_overlay(target_name);

        e.preventDefault();
        e.stopPropagation();
    });
}
