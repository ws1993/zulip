import render_confirm_unstar_all_messages from "../templates/confirm_dialog/confirm_unstar_all_messages.hbs";
import render_confirm_unstar_all_messages_in_topic from "../templates/confirm_dialog/confirm_unstar_all_messages_in_topic.hbs";

import * as confirm_dialog from "./confirm_dialog.ts";
import {$t_html} from "./i18n.ts";
import * as left_sidebar_navigation_area from "./left_sidebar_navigation_area.ts";
import * as message_flags from "./message_flags.ts";
import * as message_live_update from "./message_live_update.ts";
import * as message_store from "./message_store.ts";
import type {Message} from "./message_store.ts";
import * as popover_menus from "./popover_menus.ts";
import * as starred_messages from "./starred_messages.ts";
import * as sub_store from "./sub_store.ts";
import * as unread_ops from "./unread_ops.ts";
import {user_settings} from "./user_settings.ts";
import * as util from "./util.ts";

export function toggle_starred_and_update_server(message: Message): void {
    if (message.locally_echoed) {
        // This is defensive code for when you hit the "*" key
        // before we get a server ack.  It's rare that somebody
        // can star this quickly, and we don't have a good way
        // to tell the server which message was starred.
        return;
    }

    message.starred = !message.starred;

    // Unlike most calls to mark messages as read, we don't check
    // msg_list.can_mark_messages_read, because starring a message is an
    // explicit interaction and we'd like to preserve the user
    // expectation invariant that all starred messages are read.
    unread_ops.notify_server_message_read(message);
    message_live_update.update_starred_view(message.id, message.starred);

    if (message.starred) {
        message_flags.send_flag_update_for_messages([message.id], "starred", "add");
        starred_messages.add([message.id]);
        rerender_ui();
    } else {
        message_flags.send_flag_update_for_messages([message.id], "starred", "remove");
        starred_messages.remove([message.id]);
        rerender_ui();
    }
}

// This updates the state of the starred flag in local data
// structures, and triggers a UI rerender.
export function update_starred_flag(message_id: number, updated_starred_flag: boolean): void {
    const message = message_store.get(message_id);
    if (message === undefined) {
        // If we don't have the message locally, do nothing; if later
        // we fetch it, it'll come with the correct `starred` state.
        return;
    }
    message.starred = updated_starred_flag;
    message_live_update.update_starred_view(message_id, updated_starred_flag);
}

export function rerender_ui(): void {
    const count = starred_messages.get_count();
    let hidden = false;

    if (!user_settings.starred_message_counts) {
        // This essentially hides the count
        hidden = true;
    }

    popover_menus.get_topic_menu_popover()?.hide();
    popover_menus.get_starred_messages_popover()?.hide();
    left_sidebar_navigation_area.update_starred_count(count, hidden);
}

export function confirm_unstar_all_messages(): void {
    const html_body = render_confirm_unstar_all_messages();

    confirm_dialog.launch({
        html_heading: $t_html({defaultMessage: "Unstar all messages"}),
        html_body,
        on_click: message_flags.unstar_all_messages,
    });
}

export function confirm_unstar_all_messages_in_topic(stream_id: number, topic: string): void {
    function on_click(): void {
        message_flags.unstar_all_messages_in_topic(stream_id, topic);
    }

    const stream_name = sub_store.maybe_get_stream_name(stream_id);
    if (stream_name === undefined) {
        return;
    }

    const html_body = render_confirm_unstar_all_messages_in_topic({
        stream_name,
        topic_display_name: util.get_final_topic_display_name(topic),
        is_empty_string_topic: topic === "",
    });

    confirm_dialog.launch({
        html_heading: $t_html({defaultMessage: "Unstar messages in topic"}),
        html_body,
        on_click,
    });
}

export function initialize(): void {
    rerender_ui();
}
