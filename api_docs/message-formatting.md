# Message formatting

Zulip supports an extended version of Markdown for messages, as well as
some HTML level special behavior. The Zulip help center article on [message
formatting](/help/format-your-message-using-markdown) is the primary
documentation for Zulip's markup features. This article is currently a
changelog for updates to these features.

The [render a message](/api/render-message) endpoint can be used to get
the current HTML version of any Markdown syntax for message content.

## Code blocks

**Changes**: As of Zulip 4.0 (feature level 33), [code blocks][help-code]
can have a `data-code-language` attribute attached to the outer HTML
`div` element, which records the programming language that was selected
for syntax highlighting. This field is used in the
[playgrounds][help-playgrounds] feature for code blocks.

## Global times

**Changes**: In Zulip 3.0 (feature level 8), added [global time
mentions][help-global-time] to supported Markdown message formatting
features.

## Links to channels, topics, and messages

Zulip's markup supports special readable Markdown syntax for [linking
to channels, topics, and messages](/help/link-to-a-message-or-conversation).

Sample HTML formats are as follows:
``` html
<!-- Syntax: #**announce** -->
<a class="stream" data-stream-id="9"
  href="/#narrow/channel/9-announce">
 #announce
</a>

<!-- Syntax: #**announce>Zulip updates** -->
<a class="stream-topic" data-stream-id="9"
  href="/#narrow/channel/9-announce/topic/Zulip.20updates">
 #announce &gt; Zulip updates
</a>

<!-- Syntax: #**announce>Zulip updates@214** -->
<a class="message-link"
  href="/#narrow/channel/9-announce/topic/Zulip.20updates/near/214">
 #announce &gt; Zulip updates @ 💬
</a>
```

The older stream/topic elements include a `data-stream-id`, which
historically was used in order to display the current channel name if
the channel had been renamed. That field is **deprecated**, because
displaying an updated value for the most common forms of this syntax
requires parsing the URL to get the topic to use anyway.

When a topic is an empty string, it is replaced with
`realm_empty_topic_display_name` found in the [`POST /register`](/api/register-queue)
response and wrapped with the `<em>` tag.

Sample HTML formats with `"realm_empty_topic_display_name": "general chat"`
are as follows:
```html
<!-- Syntax: #**announce>** -->
<a class="stream-topic" data-stream-id="9"
  href="/#narrow/channel/9-announce/topic/">
 #announce &gt; <em>general chat</em>
</a>

<!-- Syntax: #**announce>@214** -->
<a class="message-link"
  href="/#narrow/channel/9-announce/topic//near/214">
 #announce &gt; <em>general chat</em> @ 💬
</a>
```

**Changes**: Before Zulip 10.0 (feature level 346), empty string
was not a valid topic name in syntaxes for linking to topics and
messages.

In Zulip 10.0 (feature level 319), added Markdown syntax
for linking to a specific message in a conversation. Declared the
`data-stream-id` field to be deprecated as detailed above.

## Image previews

When a Zulip message is sent linking to an uploaded image, Zulip will
generate an image preview element with the following format.

``` html
<div class="message_inline_image">
    <a href="/user_uploads/path/to/image.png" title="image.png">
        <img data-original-dimensions="1920x1080"
          data-original-content-type="image/png"
          src="/user_uploads/thumbnail/path/to/image.png/840x560.webp">
    </a>
</div>
```

If the server has not yet generated thumbnails for the image yet at
the time the message is sent, the `img` element will be a temporary
loading indicator image and have the `image-loading-placeholder`
class, which clients can use to identify loading indicators and
replace them with a more native loading indicator element if
desired. For example:

``` html
<div class="message_inline_image">
    <a href="/user_uploads/path/to/image.png" title="image.png">
        <img class="image-loading-placeholder"
          data-original-dimensions="1920x1080"
          data-original-content-type="image/png"
          src="/path/to/spinner.png">
    </a>
</div>
```

Once the server has a working thumbnail, such messages will be updated
via an `update_message` event, with the `rendering_only: true` flag
(telling clients not to adjust message edit history), with appropriate
adjusted `rendered_content`. A client should process those events by
just using the updated rendering. If thumbnailing failed, the same
type of event will edit the message's rendered form to remove the
image preview element, so no special client-side logic should be
required to process such errors.

Note that in the uncommon situation that the thumbnailing system is
backlogged, an individual message containing multiple image previews
may be re-rendered multiple times as each image finishes thumbnailing
and triggers a message update.

Clients are recommended to do the following when processing image
previews:

- Clients that would like to use the image's aspect ratio to lay out
  one or more images in the message feed may use the
  `data-original-dimensions` attribute, which is present even if the
  image is a placeholder spinner.  This attribute encodes the
  dimensions of the original image as `{width}x{height}`.  These
  dimensions are for the image as rendered, _after_ any EXIF rotation
  and mirroring has been applied.
- If the client would like to control the thumbnail resolution used,
  it can replace the final section of the URL (`840x560.webp` in the
  example above) with the `name` of its preferred format from the set
  of supported formats provided by the server in the
  `server_thumbnail_formats` portion of the `register`
  response. Clients should not make any assumptions about what format
  the server will use as the "default" thumbnail resolution, as it may
  change over time.
- Download button type elements should provide the original image
  (encoded via the `href` of the containing `a` tag).
- The content-type of the original image is provided on a
  `data-original-content-type` attribute, so clients can decide if
  they are capable of rendering the original image.
- For images whose formats which are not widely-accepted by browsers
  (e.g., HEIC and TIFF), the image may contain a
  `data-transcoded-image` attribute, which specifies a high-resolution
  thumbnail format which clients may use instead of the original
  image.
- Lightbox elements for viewing an image should be designed to
  immediately display any already-downloaded thumbnail while fetching
  the original-quality image or an appropriate higher-quality
  thumbnail from the server, to be transparently swapped in once it is
  available. Clients that would like to size the lightbox based on the
  size of the original image can use the `data-original-dimensions`
  attribute, as described above.
- Animated images will have a `data-animated` attribute on the `img`
  tag. As detailed in `server_thumbnail_formats`, both animated and
  still images are available for clients to use, depending on their
  preference. See, for example, the [web setting][help-previews]
  to control whether animated images are autoplayed in the message
  feed.
- Clients should not assume that the requested format is the format
  that they will receive; in rare cases where the client has an
  out-of-date list of `server_thumbnail_formats`, the server will
  provide an approximation of the client's requested format.  Because
  of this, clients should not assume that the pixel dimensions or file
  format match what they requested.
- No other processing of the URLs is recommended.

**Changes**: In Zulip 10.0 (feature level 336), added
`data-original-content-type` attribute to convey the type of the
original image, and optional `data-transcoded-image` attribute for
images with formats which are not widely supported by browsers.

**Changes**: In Zulip 9.2 (feature levels 278-279, and 287+), added
`data-original-dimensions` to the `image-loading-placeholder` spinner
images, containing the dimensions of the original image.

In Zulip 9.0 (feature level 276), added `data-original-dimensions`
attribute to images that have been thumbnailed, containing the
dimensions of the full-size version of the image. Thumbnailing itself
was reintroduced at feature level 275.

Previously, with the exception of Zulip servers that used the beta
Thumbor-based implementation years ago, all image previews in Zulip
messages were not thumbnailed; the `a` tag and the `img` tag would both
point to the original image.

Clients that correctly implement the current API should handle
Thumbor-based older thumbnails correctly, as long as they do not
assume that `data-original-dimensions` is present. Clients should not
assume that messages sent prior to the introduction of thumbnailing
have been re-rendered to use the new format or have thumbnails
available.

## Mentions and silent mentions

Zulip markup supports [mentioning](/help/mention-a-user-or-group)
users, user groups, and a few special "wildcard" mentions (the three
spellings of a channel wildcard mention: `@**all**`, `@**everyone**`,
`@**channel**` and the topic wildcard mention `@**topic**`).

Mentions result in a message being highlighted for the target user(s),
both in the UI and in notifications, and may also result in the target
user(s) following the conversation, [depending on their
settings](/help/follow-a-topic#follow-topics-where-you-are-mentioned).

Silent mentions of users or groups have none of those side effects,
but nonetheless uniquently identify the user or group
identified. (There's no such thing as a silent wildcard mention).

Permissions for mentioning users work as follows:

- Any user can mention any other user, though mentions by [muted
users](/help/mute-a-user) are automatically marked as read and thus do
not trigger notifications or otherwise get highlighted like unread
mentions.

- Wildcard mentions are permitted except where [organization-level
restrictions](/help/restrict-wildcard-mentions) apply.

- User groups can be mentioned if and only if the acting user is in
the `can_mention_group` group for that group. All user groups can be
silently mentioned by any user.

- System groups, when (silently) mentioned, should be displayed using
their description, not their `role:nobody` style API names; see the
main [system group
documentation](/api/group-setting-values#system-groups) for
details. System groups can only be silently mentioned right now,
because they happen to all use the empty `Nobody` group for
`can_mention_group`; clients should just use `can_mention_group` to
determine which groups to offer in typeahead in similar contexts.

- Requests to send or edit a message that are impermissible due to
including a mention where the acting user does not have permission to
mention the target will return an error. Mention syntax that does not
correspond to a real user or group is ignored.

Sample markup for `@**Example User**`:

``` html
<span class="user-mention" data-user-id="31">@Example User</span>
```

Sample markup for `@_**Example User**`:

``` html
<span class="user-mention silent" data-user-id="31">Example User</span>
```

Sample markup for `@**topic**`:

``` html
<span class="topic-mention">@topic</span>
```

Sample markup for `@**channel**`:

``` html
<span class="user-mention channel-wildcard-mention"
  data-user-id="*">@channel</span>
```

Sample markup for `@*support*`, assuming "support" is a valid group:
``` html
<span class="user-group-mention"
  data-user-group-id="17">@support</span>
```

Sample markup for `@_*support*`, assuming "support" is a valid group:
``` html
<span class="user-group-mention silent"
  data-user-group-id="17">support</span>
```

Sample markup for `@_*role:administrators*`:
``` html
<span class="user-group-mention silent"
  data-user-group-id="5">Administrators</span>
```

When processing mentions, clients should look up the user or group
referenced by ID, and update the textual name for the mention to the
current name for the user or group with that ID. Note that for system
groups, this requires special logic to look up the user-facing name
for that group; see [system
groups](/api/group-setting-values#system-groups) for details.

**Changes**: Prior to Zulip 10.0 (feature level 333), it was not
possible to silently mention [system
groups](/api/group-setting-values#system-groups).

In Zulip 9.0 (feature level 247), `channel` was added to the supported
[wildcard][help-mention-all] options used in the
[mentions][help-mentions] Markdown message formatting feature.

## Spoilers

**Changes**: In Zulip 3.0 (feature level 15), added
[spoilers][help-spoilers] to supported Markdown message formatting
features.

## Removed features

**Changes**: In Zulip 4.0 (feature level 24), the rarely used `!avatar()`
and `!gravatar()` markup syntax, which was never documented and had an
inconsistent syntax, were removed.

## Related articles

* [Markdown formatting](/help/format-your-message-using-markdown)
* [Send a message](/api/send-message)
* [Render a message](/api/render-message)

[help-code]: /help/code-blocks
[help-playgrounds]: /help/code-blocks#code-playgrounds
[help-spoilers]: /help/spoilers
[help-global-time]: /help/global-times
[help-mentions]: /help/mention-a-user-or-group
[help-mention-all]: /help/mention-a-user-or-group#mention-everyone-on-a-channel
[help-previews]: /help/image-video-and-website-previews#configure-how-animated-images-are-played
