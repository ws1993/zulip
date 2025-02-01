"use strict";

const assert = require("node:assert/strict");

const {mock_esm, set_global, zrequire} = require("./lib/namespace.cjs");
const {run_test, noop} = require("./lib/test.cjs");
const $ = require("./lib/zjquery.cjs");

const bootstrap_typeahead = mock_esm("../src/bootstrap_typeahead");
const search_suggestion = mock_esm("../src/search_suggestion");

const search = zrequire("search");
const search_pill = zrequire("search_pill");
const stream_data = zrequire("stream_data");

function stub_pills() {
    const $pill_container = $("#searchbox-input-container.pill-container");
    const $pill_input = $.create("pill_input");
    $pill_container.set_find_results(".input", $pill_input);
    $pill_input.before = noop;
}

set_global("getSelection", () => ({
    modify: noop,
}));

let typeahead_forced_open = false;

const verona = {
    subscribed: true,
    color: "blue",
    name: "Verona",
    stream_id: 1,
};
stream_data.add_sub(verona);

run_test("initialize", ({override, override_rewire, mock_template}) => {
    const $search_query_box = $("#search_query");
    const $searchbox_form = $("#searchbox_form");
    stub_pills();

    mock_template("search_list_item.hbs", true, (data, html) => {
        assert.equal(typeof data.description_html, "string");
        if (data.is_people) {
            for (const user of data.users) {
                assert.equal(typeof user.user_pill_context.id, "number");
                assert.equal(typeof user.user_pill_context.display_value, "string");
                assert.equal(typeof user.user_pill_context.has_image, "boolean");
                assert.equal(typeof user.user_pill_context.img_src, "string");
            }
        }
        return html;
    });

    let expected_pill_display_value = "";
    let input_pill_displayed = false;
    mock_template("input_pill.hbs", true, (data, html) => {
        assert.equal(data.display_value, expected_pill_display_value);
        input_pill_displayed = true;
        return html;
    });

    search_suggestion.max_num_of_search_results = 999;
    let terms;

    function mock_pill_removes(widget) {
        const pills = widget._get_pills_for_testing();
        for (const pill of pills) {
            pill.$element.remove = noop;
        }
    }

    override(bootstrap_typeahead, "Typeahead", (input_element, opts) => {
        assert.equal(input_element.$element, $search_query_box);
        assert.equal(opts.items, 999);
        assert.equal(opts.helpOnEmptyStrings, true);
        assert.equal(opts.matcher(), true);

        {
            const search_suggestions = {
                lookup_table: new Map([
                    [
                        "stream:Verona",
                        {
                            description_html: "Stream <strong>Ver</strong>ona",
                            search_string: "stream:Verona",
                        },
                    ],
                    [
                        "ver",
                        {
                            description_html: "Search for ver",
                            search_string: "ver",
                        },
                    ],
                ]),
                strings: ["ver", "stream:Verona"],
            };

            /* Test source */
            search_suggestion.get_suggestions = () => search_suggestions;
            const expected_source_value = search_suggestions.strings;
            const source = opts.source("ver");
            assert.deepStrictEqual(source, expected_source_value);

            /* Test highlighter */
            let expected_value = `<div class="search_list_item">\n    <span>Search for ver</span>\n</div>\n`;
            assert.equal(opts.highlighter_html(source[0]), expected_value);

            expected_value = `<div class="search_list_item">\n    <span>Stream <strong>Ver</strong>ona</span>\n</div>\n`;
            assert.equal(opts.highlighter_html(source[1]), expected_value);

            /* Test sorter */
            assert.equal(opts.sorter(search_suggestions.strings), search_suggestions.strings);
        }

        {
            const search_suggestions = {
                lookup_table: new Map([
                    [
                        "dm-including:zo",
                        {
                            description_html: "group direct messages including",
                            is_people: true,
                            search_string: "dm-including:user7@zulipdev.com",
                            users: [
                                {
                                    user_pill_context: {
                                        display_value: "<strong>Zo</strong>e",
                                        has_image: true,
                                        id: 7,
                                        img_src:
                                            "https://secure.gravatar.com/avatar/0f030c97ab51312c7bbffd3966198ced?d=identicon&version=1",
                                    },
                                },
                            ],
                        },
                    ],
                    [
                        "dm:zo",
                        {
                            description_html: "direct messages with",
                            is_people: true,
                            search_string: "dm:user7@zulipdev.com",
                            users: [
                                {
                                    user_pill_context: {
                                        display_value: "<strong>Zo</strong>e",
                                        has_image: true,
                                        id: 7,
                                        img_src:
                                            "https://secure.gravatar.com/avatar/0f030c97ab51312c7bbffd3966198ced?d=identicon&version=1",
                                    },
                                },
                            ],
                        },
                    ],
                    [
                        "sender:zo",
                        {
                            description_html: "sent by",
                            is_people: true,
                            search_string: "sender:user7@zulipdev.com",
                            users: [
                                {
                                    user_pill_context: {
                                        display_value: "<strong>Zo</strong>e",
                                        has_image: true,
                                        id: 7,
                                        img_src:
                                            "https://secure.gravatar.com/avatar/0f030c97ab51312c7bbffd3966198ced?d=identicon&version=1",
                                    },
                                },
                            ],
                        },
                    ],
                    [
                        "zo",
                        {
                            description_html: "Search for zo",
                            search_string: "zo",
                        },
                    ],
                ]),
                strings: ["zo", "sender:zo", "dm:zo", "dm-including:zo"],
            };

            /* Test source */
            search_suggestion.get_suggestions = () => search_suggestions;
            const expected_source_value = search_suggestions.strings;
            const source = opts.source("zo");
            assert.deepStrictEqual(source, expected_source_value);

            /* Test highlighter */
            let expected_value = `<div class="search_list_item">\n    <span>Search for zo</span>\n</div>\n`;
            assert.equal(opts.highlighter_html(source[0]), expected_value);

            expected_value = `<div class="search_list_item">\n    <span>sent by</span>\n        <span class="pill-container">\n            <div class='pill ' tabindex=0>\n    <img class="pill-image" src="https://secure.gravatar.com/avatar/0f030c97ab51312c7bbffd3966198ced?d&#x3D;identicon&amp;version&#x3D;1" />\n    <span class="pill-label">\n        <span class="pill-value">\n            &lt;strong&gt;Zo&lt;/strong&gt;e\n        </span></span>\n    <div class="exit">\n        <a role="button" class="zulip-icon zulip-icon-close pill-close-button"></a>\n    </div>\n</div>\n        </span>\n</div>\n`;
            assert.equal(opts.highlighter_html(source[1]), expected_value);

            expected_value = `<div class="search_list_item">\n    <span>direct messages with</span>\n        <span class="pill-container">\n            <div class='pill ' tabindex=0>\n    <img class="pill-image" src="https://secure.gravatar.com/avatar/0f030c97ab51312c7bbffd3966198ced?d&#x3D;identicon&amp;version&#x3D;1" />\n    <span class="pill-label">\n        <span class="pill-value">\n            &lt;strong&gt;Zo&lt;/strong&gt;e\n        </span></span>\n    <div class="exit">\n        <a role="button" class="zulip-icon zulip-icon-close pill-close-button"></a>\n    </div>\n</div>\n        </span>\n</div>\n`;
            assert.equal(opts.highlighter_html(source[2]), expected_value);

            expected_value = `<div class="search_list_item">\n    <span>group direct messages including</span>\n        <span class="pill-container">\n            <div class='pill ' tabindex=0>\n    <img class="pill-image" src="https://secure.gravatar.com/avatar/0f030c97ab51312c7bbffd3966198ced?d&#x3D;identicon&amp;version&#x3D;1" />\n    <span class="pill-label">\n        <span class="pill-value">\n            &lt;strong&gt;Zo&lt;/strong&gt;e\n        </span></span>\n    <div class="exit">\n        <a role="button" class="zulip-icon zulip-icon-close pill-close-button"></a>\n    </div>\n</div>\n        </span>\n</div>\n`;
            assert.equal(opts.highlighter_html(source[3]), expected_value);

            /* Test sorter */
            assert.equal(opts.sorter(search_suggestions.strings), search_suggestions.strings);
        }

        {
            /* Test updater */
            const _setup = (terms) => {
                const pills = search.search_pill_widget._get_pills_for_testing();
                for (const pill of pills) {
                    pill.$element.remove = noop;
                }
                search_pill.set_search_bar_contents(
                    terms,
                    search.search_pill_widget,
                    $search_query_box.text,
                );
            };

            terms = [
                {
                    negated: false,
                    operator: "search",
                    operand: "ver",
                },
            ];
            expected_pill_display_value = null;
            _setup(terms);
            input_pill_displayed = false;
            mock_pill_removes(search.search_pill_widget);
            $(".navbar-search.expanded").length = 1;
            assert.equal(opts.updater("ver"), "ver");
            assert.ok(!input_pill_displayed);

            const verona_stream_id = verona.stream_id.toString();
            terms = [
                {
                    negated: false,
                    operator: "channel",
                    operand: verona_stream_id,
                },
            ];
            expected_pill_display_value = "channel: Verona";
            _setup(terms);
            input_pill_displayed = false;
            mock_pill_removes(search.search_pill_widget);
            assert.equal(opts.updater(`channel:${verona_stream_id}`), "");
            assert.ok(input_pill_displayed);

            override_rewire(search, "is_using_input_method", true);
            _setup(terms);
            input_pill_displayed = false;
            mock_pill_removes(search.search_pill_widget);
            assert.equal(opts.updater(`channel:${verona_stream_id}`), "");
            assert.ok(input_pill_displayed);
        }
        return {
            lookup() {
                typeahead_forced_open = true;
            },
        };
    });

    search.initialize({
        on_narrow_search() {},
    });

    $search_query_box.text("test string");

    override_rewire(search, "is_using_input_method", false);
    $searchbox_form.trigger("compositionend");
    assert.ok(search.is_using_input_method);

    const keydown = $searchbox_form.get_on_handler("keydown");
    let default_prevented = false;
    let ev = {
        type: "keydown",
        which: 15,
        preventDefault() {
            default_prevented = true;
        },
    };
    $search_query_box.is = () => false;
    assert.equal(keydown(ev), undefined);
    assert.ok(!default_prevented);

    ev.key = "Enter";
    assert.equal(keydown(ev), undefined);
    assert.ok(!default_prevented);

    ev.key = "Enter";
    $search_query_box.is = () => true;
    assert.equal(keydown(ev), undefined);
    assert.ok(default_prevented);

    ev = {
        type: "keyup",
    };

    const _setup = (terms) => {
        const pills = search.search_pill_widget._get_pills_for_testing();
        for (const pill of pills) {
            pill.$element.remove = noop;
        }
        search_pill.set_search_bar_contents(
            terms,
            search.search_pill_widget,
            $search_query_box.text,
        );
    };

    terms = [
        {
            negated: false,
            operator: "search",
            operand: "",
        },
    ];
    _setup(terms);

    ev.key = "a";
    /* istanbul ignore next */
    $search_query_box.is = () => false;
    $searchbox_form.trigger(ev);

    let search_exited = false;
    override_rewire(search, "exit_search", () => {
        search_exited = true;
    });

    ev.key = "Enter";
    $search_query_box.is = () => false;
    $searchbox_form.trigger(ev);
    assert.ok(!search_exited);

    ev.key = "Enter";
    $search_query_box.is = () => true;
    $searchbox_form.trigger(ev);
    assert.ok(search_exited);

    let is_blurred = false;
    $search_query_box.on("blur", () => {
        is_blurred = true;
    });
    terms = [
        {
            negated: false,
            operator: "search",
            operand: "ver",
        },
    ];
    expected_pill_display_value = "ver";
    _setup(terms);
    ev.key = "Enter";
    override_rewire(search, "is_using_input_method", true);
    $searchbox_form.trigger(ev);
    // No change on first Enter keyup event
    assert.ok(!is_blurred);
    $searchbox_form.trigger(ev);
    assert.ok(is_blurred);
});

run_test("initiate_search", ({override_rewire}) => {
    let search_bar_opened = false;
    override_rewire(search, "open_search_bar_and_close_narrow_description", () => {
        search_bar_opened = true;
    });
    $(".navbar-search.expanded").length = 0;
    $("#search_query").text("");
    search.initiate_search();
    assert.ok(typeahead_forced_open);
    assert.ok(search_bar_opened);
    assert.equal($("#search_query").text(), "");
});
