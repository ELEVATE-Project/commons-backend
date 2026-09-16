from chatbot.models import StoryMedia


def get_report_images_page_html(story):

    story_media = StoryMedia.objects.filter(story=story, include_in_story=True).exclude(media_type="pdf")
    images = [media.get_public_url() for media in story_media]
    image_elements = ""
    page_html = ""

    for image in images:
        image_elements += f"""
        <div class="story-image-page-image-box" style="page-break-inside: avoid;">
            <div class='story-img-split-div'>
                <img src="{image}" alt="Story Image" class="image-report" />
            </div>
        </div>
        """

    page_html += f"""
    <div class="story-image-page-container">
      <div class="story-image-page-grid">
        {image_elements}
      </div>
    </div>
    """

    return page_html
