import $ from "jquery";

import type {InputPillConfig} from "./input_pill.ts";
import * as input_pill from "./input_pill.ts";
import type {User} from "./people.ts";
import * as people from "./people.ts";
import type {UserPill, UserPillWidget} from "./user_pill.ts";
import * as user_pill from "./user_pill.ts";
import * as util from "./util.ts";

export let widget: UserPillWidget;

const pill_config: InputPillConfig = {
    exclude_inaccessible_users: true,
};

export function initialize_pill(): UserPillWidget {
    const $container = $("#private_message_recipient").parent();

    const pill = input_pill.create({
        $container,
        pill_config,
        create_item_from_text: user_pill.create_item_from_email,
        get_text_from_item: user_pill.get_email_from_item,
        get_display_value_from_item: user_pill.get_display_value_from_item,
        generate_pill_html: (item: UserPill) => user_pill.generate_pill_html(item, true),
    });

    return pill;
}

export function initialize({
    on_pill_create_or_remove,
}: {
    on_pill_create_or_remove: () => void;
}): void {
    widget = initialize_pill();

    widget.onPillCreate(() => {
        on_pill_create_or_remove();
        $("#private_message_recipient").trigger("focus");
    });

    widget.onPillRemove(() => {
        on_pill_create_or_remove();
    });
}

export function clear(): void {
    widget.clear();
}

export function set_from_typeahead(person: User): void {
    const current_user_ids = get_user_ids();

    // Remove current user from recipient if user adds other recipient
    if (current_user_ids.length === 1 && current_user_ids.at(0) === people.my_current_user_id()) {
        clear();
    }
    user_pill.append_person({
        pill_widget: widget,
        person,
    });
}

export let set_from_emails = (value: string): void => {
    // value is something like "alice@example.com,bob@example.com"
    clear();
    widget.appendValue(value);
};

export function rewire_set_from_emails(value: typeof set_from_emails): void {
    set_from_emails = value;
}

export function get_user_ids(): number[] {
    return user_pill.get_user_ids(widget);
}

export function has_unconverted_data(): boolean {
    return user_pill.has_unconverted_data(widget);
}

export function get_user_ids_string(): string {
    const user_ids = get_user_ids();
    const sorted_user_ids = util.sorted_ids(user_ids);
    const user_ids_string = sorted_user_ids.join(",");
    return user_ids_string;
}

export let get_emails = (): string => {
    // return something like "alice@example.com,bob@example.com"
    const user_ids = get_user_ids();
    const emails = user_ids.map((id) => people.get_by_user_id(id).email).join(",");
    return emails;
};

export function rewire_get_emails(value: typeof get_emails): void {
    get_emails = value;
}

export function filter_taken_users(persons: User[]): User[] {
    return user_pill.filter_taken_users(persons, widget);
}
