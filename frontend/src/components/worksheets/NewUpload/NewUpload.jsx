// @flow
import * as React from 'react';
import $ from 'jquery';
import { withStyles } from '@material-ui/core/styles';
import Button from '@material-ui/core/Button';
import Grid from '@material-ui/core/Grid';
import Typography from '@material-ui/core/Typography';
import Input from '@material-ui/core/Input';
import UploadIcon from '@material-ui/icons/CloudUpload';

import {
    createDefaultBundleName,
    pathIsArchive,
    getArchiveExt,
    getDefaultBundleMetadata,
    createAlertText,
    createHandleRedirectFn,
} from '../../../util/worksheet_utils';
import ConfigPanel, {
    ConfigLabel,
    ConfigTextInput,
    ConfigChipInput,
    ConfigCodeInput,
    ConfigSwitchInput,
} from '../ConfigPanel';


// React doesn't support transpilation of directory and
// webkitdirectory properties, have to set them
// programmatically.
class InputDir extends React.Component {
  
  componentDidMount() {
    this.inputDir.directory = true;
    this.inputDir.webkitdirectory = true;
  }

  render() {
    const { eleref, ...others } = this.props;
    return <input
      {...others}
      type="file"
      ref={ (ele) => { this.inputDir = ele; eleref(ele); } }
    />;
  }
}

function getQueryParams(filename) {
    const formattedFilename = createDefaultBundleName(filename);
    const queryParams = {
        finalize: 1,
        filename: pathIsArchive(filename)
            ? formattedFilename + getArchiveExt(filename)
            : formattedFilename,
        unpack: pathIsArchive(filename) ? 1 : 0,
    };
    return $.param(queryParams);
}

class NewUpload extends React.Component<{
    /** JSS styling object. */
    classes: {},

    /** The worksheet to insert into **/
    worksheetUUID: string,

    /** Insert after this bundle **/
    after_sort_key: string,
}, {
    /** Uploaded data. */
    url: string,

    /** Configuration info. */
    name: string,
    description: string,
    tags: string[],
}> {

    defaultConfig = {
        name: 'untitled-upload',
        description: '',
        tags: [],
    }

    /**
     * Constructor.
     * @param props
     */
    constructor(props) {
        super(props);
        this.state = {
            ...this.defaultConfig,
        };
    }

    dropFile = (e) => {
        e.target.style.opacity = 1.0;
        e.preventDefault();
        e.stopPropagation();

        const files = this.inputFile.files;
        const { after_sort_key, worksheetUUID } = this.props;
        console.log('===>', worksheetUUID, after_sort_key, files);
        this.uploadFile(files[0]);
    }

    dropDir = (e) => {
        let dt = e.dataTransfer;
        let files = dt.files;

        // TODO: actually post files to BE
        e.target.style.opacity = 1.0;
        e.preventDefault();
        e.stopPropagation();
    }

    highlight = (e) => {
        e.target.style.opacity = .5;
        e.preventDefault();
        e.stopPropagation();
    }

    unhighlight = (e) => {
        e.target.style.opacity = 1.0;
        e.preventDefault();
        e.stopPropagation();
    }

    uploadFile = (file) => {
        if (!file) {
            return;
        }
        const { worksheetUUID, after_sort_key } = this.props;
        const createBundleData = getDefaultBundleMetadata(file.name);
        $.ajax({
            url: `/rest/bundles?worksheet=${ worksheetUUID }&after_sort_key=${ after_sort_key }`,
            data: JSON.stringify(createBundleData),
            contentType: 'application/json',
            type: 'POST',
            success: (data, status, jqXHR) => {
                var bundleUuid = data.data[0].id;
                // var fileEntryKey = this.addUploading(file.name, bundleUuid);
                // var progressbar = $('#' + PROGRESS_BAR_ID + bundleUuid);
                // var progressLabel = $('#' + PROGRESS_LABEL_ID + bundleUuid);
                // progressbar.progressbar({
                //     value: 0,
                //     max: 100,
                //     create: function() {
                //         progressLabel.text(
                //             'Uploading ' +
                //                 createDefaultBundleName(file.name) +
                //                 '.\n' +
                //                 '0% completed.',
                //         );
                //     },
                //     change: function() {
                //         progressLabel.text(
                //             'Uploading ' +
                //                 createDefaultBundleName(file.name) +
                //                 '.\n' +
                //                 progressbar.progressbar('value') +
                //                 '% completed.',
                //         );
                //     },
                //     complete: function() {
                //         progressLabel.text('Waiting for server to finish processing bundle.');
                //     },
                // });
                var reader = new FileReader();
                reader.onload = () => {
                    var arrayBuffer = reader.result,
                        bytesArray = new Uint8Array(arrayBuffer);
                    var url =
                        '/rest/bundles/' +
                        bundleUuid +
                        '/contents/blob/?' +
                        getQueryParams(file.name);
                    $.ajax({
                        url: url,
                        type: 'PUT',
                        contentType: 'application/octet-stream',
                        data: new Blob([bytesArray]),
                        processData: false,
                        xhr: function() {
                            var xhr = new window.XMLHttpRequest();
                            xhr.upload.addEventListener(
                                'progress',
                                function(evt) {
                                    // if (evt.lengthComputable) {
                                    //     var percentComplete = parseInt(
                                    //         (evt.loaded / evt.total) * 100,
                                    //     );
                                    //     progressbar.progressbar('value', percentComplete);
                                    // }
                                },
                                false,
                            );
                            return xhr;
                        },
                        success: (data, status, jqXHR) => {
                            // this.clearUploading(fileEntryKey);
                            this.props.reloadWorksheet();
                        },
                        error: (jqHXR, status, error) => {
                            // this.clearUploading(fileEntryKey);
                            alert(
                                createAlertText(
                                    reader.url,
                                    jqHXR.responseText,
                                    'refresh and try again.',
                                ),
                            );
                        },
                    });
                };
                reader.readAsArrayBuffer(file);
            },
            error: (jqHXR, status, error) => {
                alert(createAlertText(this.url, jqHXR.responseText));
            },
        });
    }

    render() {
        const { classes } = this.props;
        return (
            <ConfigPanel
                buttons={(
                    <div>
                        <Button
                            variant='text'
                            color='primary'
                            onClick={() => this.setState(this.defaultConfig)}
                        >Clear</Button>
                        <Button
                            variant='contained'
                            color='primary'
                            onClick={() => alert("New Upload Confirmed")}
                        >Confirm</Button>
                    </div>
                )}
                sidebar={(
                    <div>
                        <Typography variant='subtitle1'>Information</Typography>

                        <ConfigLabel
                            label="Name"
                            tooltip="Short name (not necessarily unique) to provide an
                            easy, human-readable way to reference this bundle (e.g as a
                            dependency). May only use alphanumeric characters and dashes."
                        />
                        <ConfigTextInput
                            value={this.state.name}
                            onValueChange={(value) => this.setState({ name: value })}
                            placeholder="untitled-upload"
                        />

                        <ConfigLabel
                            label="Description"
                            tooltip="Text description or notes about this bundle."
                            optional
                        />
                        <ConfigTextInput
                            value={this.state.description}
                            onValueChange={(value) => this.setState({ description: value })}
                            multiline
                            maxRows={3}
                        />

                        <ConfigLabel
                            label="Tags"
                            tooltip="Keywords that can be used to search for and categorize
                            this bundle."
                            optional
                        />
                        <ConfigChipInput
                            values={this.state.tags}
                            onValueAdd={(value) => this.setState(
                                (state) => ({ tags: [...state.tags, value] })
                            )}
                            onValueDelete={(value, idx) => this.setState(
                                (state) => ({ tags: [...state.tags.slice(0, idx), ...state.tags.slice(idx+1)] })
                            )}
                        />
                    </div>
                )}
            >
                {/* Main Content ------------------------------------------------------- */}
                <Typography variant='subtitle1' gutterBottom>New Upload</Typography>

                <ConfigLabel
                    label="Upload directory"
                    tooltip="Create a bundle from a directory/folder from your filesystem."
                />
                <div
                    style={ {
                        ...styles.inputBoxStyle,
                        backgroundColor: 'rgba(85, 128, 168, 0.2)',
                        borderColor: 'rgba(85, 128, 168, 0.2)',
                            padding: 16,
                    } }
                    onClick={ () => { this.inputDir.click(); } }
                    onDrop={ this.dropDir }
                    onDragOver={ this.highlight }
                    onDragLeave={ this.unhighlight }
                >
                    <InputDir
                        eleref={ (ele) => { this.inputDir = ele; } }
                        style={ { visibility: 'hidden', position: 'absolute' } }
                    />
                    <div style={ styles.greyText }>Click or drag & drop here</div>
                </div>

                <div className={classes.spacer}/>
                <ConfigLabel
                    label="Upload file"
                    tooltip="Upload a bundle with a single file from your filesystem."
                />
                <div
                    style={ {
                        ...styles.inputBoxStyle,
                        backgroundColor: 'rgba(255, 175, 125, 0.2)',
                        borderColor: 'rgba(255, 175, 125, 0.2)',
                        padding: 16,
                    } }
                    onClick={ () => { this.inputFile.click(); } }
                    onDrop={ this.dropFile }
                    onDragOver={ this.highlight }
                    onDragLeave={ this.unhighlight }
                >
                    <input
                        type="file"
                        style={ { visibility: 'hidden', position: 'absolute' } }
                        ref={ (ele) => { this.inputFile = ele; } }
                        onChange={ this.dropFile }
                    />
                    <div style={ styles.greyText }>Click or drag & drop here</div>
                </div>

                <div className={classes.spacer}/>
                <ConfigLabel
                    label="Clone from URL"
                    tooltip="Clone an existing bundle on Codalab."
                />
                <ConfigTextInput
                    value={this.state.url}
                    onValueChange={(value) => this.setState({ url: value })}/>

            </ConfigPanel>
        );
    }
}

const styles = (theme) => ({
    spacer: {
        marginTop: theme.spacing.larger,
    },
    blueText: {
    color: '#225EA8',
    },
    greyText: {
    color: '#666666',
    },
    inputBoxStyle: {
        textAlign: 'center',
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: 200,
    borderRadius: 8,
    border: '2px dashed',
    cursor: 'pointer',
    }
});

export default withStyles(styles)(NewUpload);
