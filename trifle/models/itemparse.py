import json
import os
import lxml.html
import lxml.html.clean

from trifle.utils import short_id, CONTENT_PATH

def process_item(item):
    """
    Should return a (dictionary, content,) pair.
    Dictionary should contain subscription, time, href, author, title and
    summary fields.
    If any of values doesn't exist, they'll be replaced with meaningful
    defaults. For example "Unknown" for author or "Untitled item" for
    title
    """
    # After a lot of fiddling around I realized one thing. We are IN NO
    # WAY guaranteed that any of these fields exists at all.
    # This idiocy should make this method bigger than a manpage for
    # understanding teenage girls' thought processes.
    content = item['content']['content'] if 'content' in item else \
              item['summary']['content'] if 'summary' in item else ''

    fragments = lxml.html.fragments_fromstring(content)
    main = lxml.html.HtmlElement()
    main.tag = 'div'
    # Put fragments all under one element for easier manipulation
    if len(fragments) > 0 and isinstance(fragments[0], str):
        main.text = fragments[0]
        del fragments[0]
    for key, fragment in enumerate(fragments):
        if isinstance(fragment, lxml.html.HtmlElement):
            main.append(fragment)
        else:
            main[-1].tail = fragment

    # Get summary text before all the modifications.
    summary = main.text_content().replace('\n', ' ').strip()[:250]

    # Replace all iframes with regular link
    for iframe in main.xpath('//iframe'):
        src = iframe.get('src')
        if not src:
            iframe.getparent().remove(iframe)
        else:
            link = lxml.html.HtmlElement(src, attrib = {
                                                    'href': src,
                                                    'class':'trifle_iframe'})
            link.tag = 'a'
            iframe.getparent().replace(iframe, link)

    # Remove following attributes from elements
    remove = ('width', 'height', 'color', 'size', 'align', 'background',
              'bgcolor', 'border', 'cellpadding', 'cellspacing',)
    xpath = '//*[{0}]'.format(' or '.join('@'+a for a in remove))
    for el in main.xpath(xpath):
        attrib = el.attrib
        for attr in remove:
            if attr in attrib:
                attrib.pop(attr)

    content = lxml.html.tostring(main, encoding='unicode')
    cleaner = lxml.html.clean.Cleaner()
    cleaner.remove_tags = ['font']
    content = cleaner.clean_html(content)

    time = int(item['timestampUsec'])
    if time >= int(item.get('updated', -1)) * 1E6:
        time = item['updated'] * 1E6
    try:
        href = item['alternate'][0]['href']
    except KeyError:
        href = item['origin']['htmlUrl']

    title = item.get('title', None)
    if title is not None:
        title = lxml.html.fromstring(title).text_content().strip()

    return {'title': title, 'summary': summary, 'href': href,
            'author': item.get('author', None), 'time': time,
            'subscription': item['origin']['streamId']}, content


def process_items(data):
    data = json.loads(data)
    resp = []
    for item in data['items']:
        sid = short_id(item['id'])
        metadata, content = process_item(item)
        # There's no need to replace this one with asynchronous operation as
        # we do everything here in another process anyway.
        fpath = os.path.join(CONTENT_PATH, str(sid))
        with open(fpath, 'w') as f:
            f.write(content)
        metadata.update({'id': sid})
        resp.append(metadata)
    return resp



