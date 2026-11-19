
<?php echo '<?'?>
xml version="1.0" encoding="UTF-8"?>
<rss xmlns:metaInfo="http://foobar" version="2.0">
    <channel>
    <title>phpGraphy <?php echo $this->_vars['page_title']; ?>
</title>
    <link><?php echo $this->_vars['page_uri']; ?>
/</link>
    <description>phpGraphy <?php echo $this->_vars['page_title']; ?>
</description>
    <?php if (count((array)$this->_vars['pictures'])): foreach ((array)$this->_vars['pictures'] as $this->_vars['picture']): ?>
    <item>
        <title><?php if ($this->_vars['mode'] == "toprated"):  echo $this->_vars['picture']['X_with_X_votes'];  elseif ($this->_vars['mode'] == "lastaddedpictures"):  echo $this->_vars['picture']['datetime'];  elseif ($this->_vars['mode'] == "lastcommented"):  echo $this->_vars['picture']['datetime']; ?>
 <?php echo $this->_vars['txt_comment_by']; ?>
 <?php echo $this->_vars['picture']['by'];  endif; ?></title>
        <link><?php echo $this->_vars['page_uri']; ?>
?display=<?php echo $this->_vars['picture']['picurl']; ?>
</link>
        <guid><?php echo $this->_vars['page_uri']; ?>
?display=<?php echo $this->_vars['picture']['picurl']; ?>
</guid>
        <description><![CDATA[
        <table border="0">
        <tr><td>
            <?php if ($this->_vars['mode'] == "toprated"): ?>
            <span class="small"><?php echo $this->_vars['picture']['place']; ?>
.</span>
            <?php endif; ?>
            <a href="<?php echo $this->_vars['page_uri']; ?>
?display=<?php echo $this->_vars['picture']['picurl']; ?>
" title="<?php echo $this->_vars['picture']['pictitle']; ?>
">
            <img src="<?php echo $this->_vars['page_uri']; ?>
?previewpic=<?php echo $this->_vars['picture']['picurl']; ?>
" alt="<?php echo $this->_vars['picture']['pictitle']; ?>
" class="thumbnail" />
            </a>
        </td>
        <td>

            <a href="<?php echo $this->_vars['page_uri']; ?>
?display=<?php echo $this->_vars['picture']['picurl']; ?>
"><?php echo $this->_vars['picture']['pictitle']; ?>
</a>

            <?php if ($this->_vars['mode'] == "toprated"): ?>
            <span class="small"> - <?php echo $this->_vars['picture']['X_with_X_votes']; ?>
</span>
            <?php elseif ($this->_vars['mode'] == "lastaddedpictures"): ?>
            <div class="small"><?php echo $this->_vars['picture']['datetime']; ?>
</div>
            <?php elseif ($this->_vars['mode'] == "lastcommented"): ?>
            <span class="small"><?php echo $this->_vars['picture']['datetime']; ?>
 <?php echo $this->_vars['txt_comment_by']; ?>
 <b><?php echo $this->_vars['picture']['by']; ?>
</b></span>
            <?php endif; ?>

        </td></tr>
        </table>
        ]]></description>
    </item>
    <?php endforeach; endif; ?>
    </channel>
</rss>
